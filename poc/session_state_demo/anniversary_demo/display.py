"""
Anniversary Demo Display
=========================

Enhanced display utilities for the 30-turn demo.
Beautiful terminal output with colors, boxes, progress bars,
and dramatic effects for key moments.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List


def setup_unicode_console() -> None:
    """Enable Unicode output in Windows PowerShell/CMD."""
    if sys.platform == "win32":
        # Set console to UTF-8
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)  # UTF-8
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        # Also set Python's stdout encoding
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass


# Call on import
setup_unicode_console()


# ============================================================================
# Unicode Box-Drawing Characters
# ============================================================================

# Corners
TL = "\u250c"  # Top-left corner
TR = "\u2510"  # Top-right corner
BL = "\u2514"  # Bottom-left corner
BR = "\u2518"  # Bottom-right corner

# Lines
HZ = "\u2500"  # Horizontal line
VT = "\u2502"  # Vertical line

# Heavy variants
TL_H = "\u250f"  # Heavy top-left
TR_H = "\u2513"  # Heavy top-right
BL_H = "\u2517"  # Heavy bottom-left
BR_H = "\u251b"  # Heavy bottom-right
HZ_H = "\u2501"  # Heavy horizontal
VT_H = "\u2503"  # Heavy vertical

# Double-line variants
TL_D = "\u2554"  # Double top-left
TR_D = "\u2557"  # Double top-right
BL_D = "\u255a"  # Double bottom-left
BR_D = "\u255d"  # Double bottom-right
HZ_D = "\u2550"  # Double horizontal
VT_D = "\u2551"  # Double vertical

# Block characters
FULL_BLOCK = "\u2588"  # Full block
LIGHT_SHADE = "\u2591"  # Light shade
MED_SHADE = "\u2592"  # Medium shade
DARK_SHADE = "\u2593"  # Dark shade

# Progress bar
PROG_FULL = "\u2588"  # Full block for progress
PROG_EMPTY = "\u2591"  # Light shade for empty

# Symbols
CHECK = "\u2713"  # Check mark
CROSS = "\u2717"  # Cross mark
ARROW_R = "\u25b6"  # Right arrow
ARROW_D = "\u25bc"  # Down arrow
BULLET = "\u2022"  # Bullet point
STAR = "\u2605"  # Star
LIGHTNING = "\u26a1"  # Lightning bolt
WARNING = "\u26a0"  # Warning sign
GEAR = "\u2699"  # Gear/settings
DATABASE = "\u25a3"  # Database symbol
CLOCK = "\u231b"  # Hourglass/clock

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
BLINK = "\033[5m"
REVERSE = "\033[7m"

# Standard colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
GRAY = "\033[90m"

# Background colors
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN = "\033[46m"
BG_WHITE = "\033[47m"


def colorize(text: str, color: str, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text."""
    prefix = ""
    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    return f"{prefix}{color}{text}{RESET}"


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system("cls" if os.name == "nt" else "clear")


# ============================================================================
# Progress Indicators
# ============================================================================


def print_progress_bar(current: int, total: int, width: int = 40, prefix: str = "") -> None:
    """Print a beautiful Unicode progress bar."""
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = PROG_FULL * filled + PROG_EMPTY * (width - filled)
    pct_str = f"{pct * 100:5.1f}%"
    print(f"\r{prefix}{TL}{colorize(bar, GREEN)}{TR} {pct_str} ({current}/{total})", end="")
    if current >= total:
        print()


def print_turn_indicator(turn: int, total: int = 30) -> None:
    """Print turn indicator in header style with Unicode."""
    act_name = ""
    act_icon = ""
    if turn <= 8:
        act_name = "SETUP & LEARNING"
        act_icon = GEAR
    elif turn <= 14:
        act_name = "GAP DETECTION"
        act_icon = WARNING
    elif turn <= 20:
        act_name = "BACKGROUND TASKS"
        act_icon = LIGHTNING
    elif turn <= 25:
        act_name = "PROACTIVE"
        act_icon = STAR
    else:
        act_name = "RESOLUTION"
        act_icon = CHECK

    pct = turn / total
    bar_width = 20
    filled = int(bar_width * pct)
    bar = colorize(PROG_FULL * filled, GREEN) + colorize(PROG_EMPTY * (bar_width - filled), GRAY)

    print()
    print(colorize(TL_D + HZ_D * 68 + TR_D, CYAN))
    print(
        colorize(VT_D, CYAN)
        + f"  {ARROW_R} Turn {turn:2d} of {total}  {TL}{bar}{TR}  {act_icon} {colorize(act_name, YELLOW, bold=True):28}"
        + colorize(VT_D, CYAN)
    )
    print(colorize(BL_D + HZ_D * 68 + BR_D, CYAN))


# ============================================================================
# Headers and Dividers
# ============================================================================


def print_demo_header() -> None:
    """Print the main demo header with ASCII art."""
    clear_screen()
    header = r"""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║        ████████╗██╗  ██╗███████╗                                  ║
    ║        ╚══██╔══╝██║  ██║██╔════╝                                  ║
    ║           ██║   ███████║█████╗                                    ║
    ║           ██║   ██╔══██║██╔══╝                                    ║
    ║           ██║   ██║  ██║███████╗                                  ║
    ║           ╚═╝   ╚═╝  ╚═╝╚══════╝                                  ║
    ║                                                                   ║
    ║     █████╗ ███╗   ██╗███╗   ██╗██╗██╗   ██╗███████╗██████╗ ███████╗║
    ║    ██╔══██╗████╗  ██║████╗  ██║██║██║   ██║██╔════╝██╔══██╗██╔════╝║
    ║    ███████║██╔██╗ ██║██╔██╗ ██║██║██║   ██║█████╗  ██████╔╝███████╗║
    ║    ██╔══██║██║╚██╗██║██║╚██╗██║██║╚██╗ ██╔╝██╔══╝  ██╔══██╗╚════██║║
    ║    ██║  ██║██║ ╚████║██║ ╚████║██║ ╚████╔╝ ███████╗██║  ██║███████║║
    ║    ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═══╝╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝╚══════╝║
    ║                                                                   ║
    ║               █╗    ██╗███████╗███████╗██╗  ██╗███████╗███╗   ██╗██████╗ ║
    ║               ██║    ██║██╔════╝██╔════╝██║ ██╔╝██╔════╝████╗  ██║██╔══██╗║
    ║               ██║ █╗ ██║█████╗  █████╗  █████╔╝ █████╗  ██╔██╗ ██║██║  ██║║
    ║               ██║███╗██║██╔══╝  ██╔══╝  ██╔═██╗ ██╔══╝  ██║╚██╗██║██║  ██║║
    ║               ╚███╔███╔╝███████╗███████╗██║  ██╗███████╗██║ ╚████║██████╔╝║
    ║                ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ ║
    ║                                                                   ║
    ║                   Mike's 50th Birthday Surprise                   ║
    ║                    A 30-Turn FamilyOS Demo                        ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """
    # Simpler header that renders properly
    print()
    print(colorize("=" * 70, CYAN))
    print(colorize("           THE ANNIVERSARY WEEKEND", CYAN, bold=True))
    print(colorize("         Mike's 50th Birthday Surprise", YELLOW))
    print(colorize("           A 30-Turn FamilyOS Demo", GRAY))
    print(colorize("=" * 70, CYAN))
    print()


def print_act_header(act_name: str, turns: str) -> None:
    """Print an act header."""
    print()
    print(colorize("*" * 70, MAGENTA))
    print(colorize(f"  {act_name}", MAGENTA, bold=True))
    print(colorize(f"  Turns: {turns}", GRAY))
    print(colorize("*" * 70, MAGENTA))
    print()


def print_divider(char: str = "-", color: str = GRAY) -> None:
    """Print a simple divider."""
    print(colorize(char * 70, color))


# ============================================================================
# Message Display
# ============================================================================


def print_user_message(content: str, is_sarah: bool = True) -> None:
    """Print user message in Sarah's style."""
    speaker = "SARAH" if is_sarah else "USER"
    print()
    print(colorize(f"{speaker}:", GREEN, bold=True))
    # Word wrap
    words = content.split()
    line = "  "
    for word in words:
        if len(line) + len(word) > 70:
            print(line)
            line = "  "
        line += word + " "
    if line.strip():
        print(line)


def print_assistant_message(content: str) -> None:
    """Print assistant/concierge message."""
    print()
    print(colorize("CONCIERGE:", BLUE, bold=True))
    # Word wrap
    words = content.split()
    line = "  "
    for word in words:
        if len(line) + len(word) > 70:
            print(line)
            line = "  "
        line += word + " "
    if line.strip():
        print(line)


def print_system_message(content: str, severity: str = "info") -> None:
    """Print system message with appropriate styling."""
    colors = {
        "info": CYAN,
        "warning": YELLOW,
        "error": RED,
        "success": GREEN,
    }
    color = colors.get(severity, CYAN)
    print()
    print(colorize(f"[SYSTEM] {content}", color))


# ============================================================================
# Tool and State Display
# ============================================================================


def print_fsm_state_transition(
    state_history: List[str],
    intent_type: str = "",
    complexity_tier: str = "",
    classification_ms: int = 0,
) -> None:
    """
    Print FSM state transitions with visual flow.

    Shows: LISTENING -> ACKING -> DISPATCHING -> EXECUTING -> DELIVERING -> LISTENING
    """
    # State colors
    state_colors = {
        "LISTENING": CYAN,
        "ACKING": YELLOW,
        "CLARIFYING": MAGENTA,
        "DISPATCHING": BLUE,
        "EXECUTING": GREEN,
        "DELIVERING": GREEN,
    }

    print()
    print(colorize(f"  {GEAR} [FSM]", BLUE, bold=True) + " State Transitions:")

    # Build transition string
    if state_history:
        transitions = []
        for i, state in enumerate(state_history):
            color = state_colors.get(state, GRAY)
            if i == len(state_history) - 1:
                # Current state - bold
                transitions.append(colorize(state, color, bold=True))
            else:
                transitions.append(colorize(state, color, dim=True))

        flow = f" {ARROW_R} ".join(transitions)
        print(f"       {flow}")

    # Show classification info if available
    if intent_type or complexity_tier:
        info_parts = []
        if intent_type:
            info_parts.append(f"Intent: {colorize(intent_type, YELLOW)}")
        if complexity_tier:
            tier_color = (
                GREEN
                if complexity_tier == "LOW"
                else YELLOW if complexity_tier == "MEDIUM" else RED
            )
            info_parts.append(f"Tier: {colorize(complexity_tier, tier_color)}")
        if classification_ms > 0:
            info_parts.append(f"Classification: {classification_ms}ms")

        if info_parts:
            print(f"       {BULLET} " + " | ".join(info_parts))


def print_tool_call(name: str, args: Dict[str, Any]) -> None:
    """Print a tool call with beautiful formatting."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    if len(args) > 3:
        args_str += ", ..."
    print(colorize(f"  {GEAR} [TOOL]", MAGENTA, bold=True) + f" {name}({args_str})")


def print_llm_call(
    model: str = "gemini",
    prompt_preview: str = "",
    message_count: int = 0,
    tool_count: int = 0,
) -> None:
    """Print LLM call being made."""
    print()
    print(colorize(f"  {LIGHTNING} [LLM CALL]", CYAN, bold=True) + f" {model}")
    if prompt_preview:
        # Truncate prompt preview to 80 chars
        preview = prompt_preview[:80] + "..." if len(prompt_preview) > 80 else prompt_preview
        print(colorize(f"       {BULLET} Prompt: ", GRAY) + f'"{preview}"')
    print(
        colorize(f"       {BULLET} Messages: {message_count} | Tools available: {tool_count}", GRAY)
    )


def print_llm_response(
    content_preview: str = "",
    tool_calls: List[Dict[str, Any]] = None,
    latency_ms: int = 0,
) -> None:
    """Print LLM response summary."""
    tool_calls = tool_calls or []
    print(colorize(f"  {CHECK} [LLM RESPONSE]", GREEN, bold=True) + f" ({latency_ms}ms)")
    if tool_calls:
        print(colorize(f"       {BULLET} Tool calls: {len(tool_calls)}", GRAY))
        for tc in tool_calls[:3]:  # Show first 3
            name = tc.get("name", "unknown")
            args_preview = str(tc.get("args", {}))[:50]
            print(colorize(f"           {ARROW_R} {name}: {args_preview}...", GRAY))
    if content_preview:
        preview = content_preview[:100] + "..." if len(content_preview) > 100 else content_preview
        print(colorize(f"       {BULLET} Response: ", GRAY) + f'"{preview}"')


def print_subagent_dispatch(
    agent_name: str,
    task: str,
    context_preview: str = "",
) -> None:
    """Print sub-agent being dispatched."""
    print()
    print(colorize(f"  {ARROW_R} [SUBAGENT]", BLUE, bold=True) + f" Dispatching {agent_name}")
    print(colorize(f"       {BULLET} Task: ", GRAY) + task[:80])
    if context_preview:
        print(colorize(f"       {BULLET} Context: ", GRAY) + context_preview[:60])


def print_subagent_response(
    agent_name: str,
    result_preview: str = "",
    latency_ms: int = 0,
    success: bool = True,
) -> None:
    """Print sub-agent response."""
    icon = CHECK if success else CROSS
    color = GREEN if success else RED
    status = "SUCCESS" if success else "FAILED"
    print(colorize(f"  {icon} [{agent_name}]", color, bold=True) + f" {status} ({latency_ms}ms)")
    if result_preview:
        preview = result_preview[:100] + "..." if len(result_preview) > 100 else result_preview
        print(colorize(f"       {BULLET} Result: ", GRAY) + f'"{preview}"')


def print_tool_execution_result(
    tool_name: str,
    success: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Print the result of tool execution (e.g., booking confirmation)."""
    icon = CHECK if success else CROSS
    color = GREEN if success else RED
    prefix = "EXECUTED" if success else "FAILED"
    print(colorize(f"    {icon} [{prefix}]", color, bold=True) + f" {tool_name}")
    print(colorize(f"         {BULLET} {message}", color))
    if data:
        # Show key details
        for key in [
            "confirmation",
            "confirmation_number",
            "property",
            "restaurant_name",
            "service_name",
        ]:
            if key in data:
                print(colorize(f"         {BULLET} {key}: {data[key]}", CYAN))


def print_gap_detection_call(
    user_input: str,
    referents: List[str] = None,
    beliefs_count: int = 0,
) -> None:
    """Print gap detection being performed."""
    referents = referents or []
    print(colorize(f"  {GEAR} [GAP DETECTOR]", YELLOW, bold=True) + " Analyzing input...")
    print(colorize(f"       {BULLET} Input: ", GRAY) + f'"{user_input[:50]}"')
    if referents:
        print(colorize(f"       {BULLET} Referents: {', '.join(referents[:5])}", GRAY))
    print(colorize(f"       {BULLET} Known facts: {beliefs_count}", GRAY))


def print_gap_detected(missing_params: List[str]) -> None:
    """Print gap detection notification."""
    print()
    print(colorize(f"  {WARNING} [GAP DETECTED]", YELLOW, bold=True))
    print(colorize(f"  {BULLET} Missing: {', '.join(missing_params)}", YELLOW))


def print_clarification(question: str) -> None:
    """Print clarification question."""
    print()
    print(colorize(f"  {BULLET} [CLARIFYING]", MAGENTA, bold=True))
    print(f"  ? {question}")


def print_background_task_started(task_type: str, task_id: str) -> None:
    """Print background task started notification."""
    print()
    print(
        colorize(f"  {LIGHTNING} [BACKGROUND]", CYAN, bold=True) + f" Started {task_type} monitor"
    )
    print(colorize(f"             {BULLET} Task ID: {task_id}", GRAY))


def print_system_activity(
    turn_num: int,
    session_ops: List[str] = None,
    tool_calls: List[str] = None,
    state_changes: Dict[str, Any] = None,
    bytes_delta: int = 0,
    latency_ms: int = 0,
) -> None:
    """
    Print a system activity panel showing all background operations.

    This shows what's happening under the hood:
    - SessionState operations (read/write)
    - Tool executions
    - State changes (beliefs, persona, bookings)
    - Memory usage
    - Performance metrics
    """
    session_ops = session_ops or []
    tool_calls = tool_calls or []
    state_changes = state_changes or {}

    print()
    print(colorize(TL_H + HZ_H * 68 + TR_H, GRAY))
    print(
        colorize(VT_H, GRAY)
        + colorize(f"  {GEAR} SYSTEM ACTIVITY - Turn {turn_num}", GRAY, bold=True).ljust(75)
        + colorize(VT_H, GRAY)
    )
    print(colorize(VT_H + HZ * 68 + VT_H, GRAY))

    # SessionState Operations
    if session_ops:
        print(
            colorize(VT_H, GRAY)
            + colorize(f"  {DATABASE} SessionState Operations:", CYAN).ljust(75)
            + colorize(VT_H, GRAY)
        )
        for op in session_ops:
            print(
                colorize(VT_H, GRAY)
                + colorize(f"     {BULLET} {op}", CYAN, dim=True).ljust(75)
                + colorize(VT_H, GRAY)
            )

    # Tool Executions
    if tool_calls:
        print(
            colorize(VT_H, GRAY)
            + colorize(f"  {GEAR} Tool Executions:", MAGENTA).ljust(75)
            + colorize(VT_H, GRAY)
        )
        for tool in tool_calls:
            print(
                colorize(VT_H, GRAY)
                + colorize(f"     {ARROW_R} {tool}", MAGENTA, dim=True).ljust(75)
                + colorize(VT_H, GRAY)
            )

    # State Changes
    if state_changes:
        print(
            colorize(VT_H, GRAY)
            + colorize(f"  {STAR} State Changes:", YELLOW).ljust(75)
            + colorize(VT_H, GRAY)
        )
        for key, value in state_changes.items():
            val_str = str(value)[:40] + "..." if len(str(value)) > 40 else str(value)
            print(
                colorize(VT_H, GRAY)
                + colorize(f"     {BULLET} {key}: {val_str}", YELLOW, dim=True).ljust(75)
                + colorize(VT_H, GRAY)
            )

    # Metrics footer
    print(colorize(VT_H + HZ * 68 + VT_H, GRAY))
    metrics = (
        f"  {CLOCK} {latency_ms}ms  {BULLET}  {bytes_delta:+} bytes  {BULLET}  {CHECK} committed"
    )
    print(
        colorize(VT_H, GRAY) + colorize(metrics, GREEN, dim=True).ljust(75) + colorize(VT_H, GRAY)
    )
    print(colorize(BL_H + HZ_H * 68 + BR_H, GRAY))


# ============================================================================
# Special Events
# ============================================================================


def print_crash_screen() -> None:
    """Print a dramatic crash screen with proper ASCII art."""
    print()

    # Dramatic red border
    border = colorize("=" * 70, RED, bold=True)
    print(border)
    print()

    # "CRASH" ASCII art - properly padded
    crash_art = [
        "              ██████╗██████╗  █████╗ ███████╗██╗  ██╗",
        "             ██╔════╝██╔══██╗██╔══██╗██╔════╝██║  ██║",
        "             ██║     ██████╔╝███████║███████╗███████║",
        "             ██║     ██╔══██╗██╔══██║╚════██║██╔══██║",
        "             ╚██████╗██║  ██║██║  ██║███████║██║  ██║",
        "              ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝",
    ]

    for line in crash_art:
        print(colorize(line, RED, bold=True))

    print()
    print(colorize("            SESSION TERMINATED UNEXPECTEDLY", WHITE, bold=True))
    print()

    # Status box
    print(colorize(TL_D + HZ_D * 50 + TR_D, RED))
    print(
        colorize(VT_D, RED)
        + f"  {CROSS} Connection lost to session manager".ljust(50)
        + colorize(VT_D, RED)
    )
    print(
        colorize(VT_D, RED)
        + f"  {CROSS} Active turn interrupted mid-execution".ljust(50)
        + colorize(VT_D, RED)
    )
    print(
        colorize(VT_D, RED)
        + colorize(f"  {CHECK} Checkpoint available: Turn 19", YELLOW).ljust(58)
        + colorize(VT_D, RED)
    )
    print(colorize(BL_D + HZ_D * 50 + BR_D, RED))

    print()
    print(border)
    time.sleep(1.5)


def print_restore_screen() -> None:
    """Print restore screen with proper ASCII art."""
    print()

    # Green border
    border = colorize("=" * 70, GREEN, bold=True)
    print(border)
    print()

    # "RESTORE" ASCII art - properly padded
    restore_art = [
        "         ██████╗ ███████╗███████╗████████╗ ██████╗ ██████╗ ███████╗",
        "         ██╔══██╗██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██╔════╝",
        "         ██████╔╝█████╗  ███████╗   ██║   ██║   ██║██████╔╝█████╗",
        "         ██╔══██╗██╔══╝  ╚════██║   ██║   ██║   ██║██╔══██╗██╔══╝",
        "         ██║  ██║███████╗███████║   ██║   ╚██████╔╝██║  ██║███████╗",
        "         ╚═╝  ╚═╝╚══════╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝",
    ]

    for line in restore_art:
        print(colorize(line, GREEN, bold=True))

    print()
    print(colorize("                  RECOVERING FROM CHECKPOINT...", WHITE, bold=True))
    print()

    # Animated restore steps
    print(colorize(TL_H + HZ_H * 56 + TR_H, CYAN))

    steps = [
        (f"  {DATABASE} Loading checkpoint from SQLite", 0.2),
        (f"  {GEAR} Deserializing FlatBuffer payload", 0.15),
        (f"  {BULLET} Restoring conversation history (19 turns)", 0.2),
        (f"  {BULLET} Restoring user preferences", 0.1),
        (f"  {BULLET} Restoring learned beliefs", 0.1),
        (f"  {BULLET} Restoring active bookings", 0.1),
        (f"  {LIGHTNING} Reconnecting background monitors", 0.15),
    ]

    for step, delay in steps:
        print(colorize(VT_H, CYAN) + colorize(step, CYAN).ljust(56) + colorize(VT_H, CYAN))
        sys.stdout.flush()
        time.sleep(delay)

    print(colorize(BL_H + HZ_H * 56 + BR_H, CYAN))

    print()
    print(colorize(f"  {CHECK} SESSION RESTORED SUCCESSFULLY", GREEN, bold=True).center(70))
    print(colorize("  All 19 turns recovered - no data lost", GREEN).center(70))
    print()
    print(border)
    time.sleep(0.5)
    print(colorize(VT_D + " " * 68 + VT_D, GREEN))

    # Bottom border
    print(colorize(BL_D + HZ_D * 68 + BR_D, GREEN, bold=True))
    time.sleep(0.5)


def print_weather_alert() -> None:
    """Print beautiful weather alert notification."""
    print()

    # Alert box with Unicode
    print(colorize(TL_D + HZ_D * 68 + TR_D, YELLOW))
    print(
        colorize(VT_D, YELLOW)
        + colorize(
            f"  {LIGHTNING} PROACTIVE ALERT - BACKGROUND MONITOR {LIGHTNING}", YELLOW, bold=True
        ).center(76)
        + colorize(VT_D, YELLOW)
    )
    print(colorize(VT_D + HZ * 68 + VT_D, YELLOW))
    print(
        colorize(VT_D, YELLOW)
        + f"  {WARNING} Weather Monitor triggered".ljust(68)
        + colorize(VT_D, YELLOW)
    )
    print(colorize(BL_D + HZ_D * 68 + BR_D, YELLOW))
    print()
    print(colorize(f"  {BULLET} Forecast change detected for Sonoma weekend:", WHITE, bold=True))
    print(f"    {BULLET} Saturday: {colorize('72°F, Sunny ' + STAR, GREEN)} (no change)")
    print(f"    {WARNING} Sunday:   {colorize('60% chance of rain afternoon', YELLOW, bold=True)}")
    print()
    print(colorize(f"  {ARROW_R} Recommendation: Consider indoor backup plans", CYAN))
    print()


# ============================================================================
# Summary and Stats
# ============================================================================


def print_trip_summary(summary: Dict[str, Any]) -> None:
    """Print the final trip summary in a beautiful Unicode box.

    Args:
        summary: Dict with optional keys:
            - bookings: List of booking dicts from ToolExecutor
            - messages: List of messages sent
            - events: List of calendar events
    """
    print()
    print(colorize(TL_D + HZ_D * 68 + TR_D, GREEN))
    print(
        colorize(VT_D, GREEN)
        + colorize(f"  {STAR} ANNIVERSARY WEEKEND SUMMARY {STAR}", GREEN, bold=True).center(76)
        + colorize(VT_D, GREEN)
    )
    print(colorize(VT_D + HZ * 68 + VT_D, GREEN))

    bookings = summary.get("bookings", [])
    messages = summary.get("messages", [])
    events = summary.get("events", [])

    # If we have real bookings, show them
    if bookings:
        for booking in bookings:
            # Determine booking type and format appropriately
            conf = booking.get("confirmation_number", booking.get("confirmation", "N/A"))
            if "property" in booking:
                # Accommodation booking
                prop = booking.get("property", "Unknown")
                check_in = booking.get("check_in", "")
                nights = booking.get("nights", 2) if "nights" in booking else ""
                cost = booking.get("total_cost", 0)
                label = f"{CHECK} Accommodation"
                value = f"{prop}"
                if check_in:
                    value += f", {check_in}"
                if nights:
                    value += f" ({nights} nights)"
                if cost:
                    value += f" - ${cost}"
                value += f" [{conf}]"
            elif "restaurant_name" in booking or "restaurant" in booking:
                # Restaurant booking
                rest = booking.get("restaurant_name", booking.get("restaurant", "Unknown"))
                date = booking.get("date", "")
                time_slot = booking.get("time", "")
                party = booking.get("party_size", "")
                label = f"{CHECK} Dinner"
                value = f"{rest}"
                if date:
                    value += f", {date}"
                if time_slot:
                    value += f" {time_slot}"
                if party:
                    value += f" ({party} guests)"
                value += f" [{conf}]"
            elif "service_name" in booking or "service" in booking:
                # Spa booking
                service = booking.get("service_name", booking.get("service", "Unknown"))
                date = booking.get("date", "")
                time_slot = booking.get("time", "")
                label = f"{CHECK} Spa"
                value = f"{service}"
                if date:
                    value += f", {date}"
                if time_slot:
                    value += f" {time_slot}"
                value += f" [{conf}]"
            else:
                # Generic booking
                label = f"{CHECK} Booking"
                value = str(booking)[:60]

            line = f"  {colorize(label + ':', CYAN)} {value}"
            # Truncate long lines
            if len(line) > 74:
                line = line[:71] + "..."
            print(colorize(VT_D, GREEN) + line.ljust(74) + colorize(VT_D, GREEN))

        # Show totals
        total_cost = sum(b.get("total_cost", b.get("price", 0)) for b in bookings)
        if total_cost:
            total_line = f"  {colorize('TOTAL COST:', YELLOW, bold=True)} ${total_cost}"
            print(colorize(VT_D, GREEN) + total_line.ljust(74) + colorize(VT_D, GREEN))
    else:
        # Fallback to static text if no real bookings
        sections = [
            (f"{CHECK} Accommodation", "Vineyard Inn, Sonoma - 2 nights (Sat-Sun)"),
            (f"{CHECK} Dinner", "Della Santina's, Saturday 7pm (shellfish allergy noted!)"),
            (f"{CHECK} Spa", "Couples massage, Sunday 11am"),
            (f"{CHECK} Transportation", "Scenic route from SF, ~1.5 hours"),
            (f"{WARNING} Weather", "Saturday sunny, Sunday rain afternoon"),
            (f"{CHECK} Family", "Emma briefed, check-in scheduled Saturday 2pm"),
            (f"{CHECK} Cover Story", "Tech Summit Napa on calendar"),
        ]

        for label, value in sections:
            line = f"  {colorize(label + ':', CYAN)} {value}"
            print(colorize(VT_D, GREEN) + line.ljust(74) + colorize(VT_D, GREEN))

    # Show messages if any
    if messages:
        msg_line = f"  {colorize(f'{len(messages)} Messages Sent', CYAN)}"
        print(colorize(VT_D, GREEN) + msg_line.ljust(74) + colorize(VT_D, GREEN))

    # Show events if any
    if events:
        evt_line = f"  {colorize(f'{len(events)} Calendar Events Created', CYAN)}"
        print(colorize(VT_D, GREEN) + evt_line.ljust(74) + colorize(VT_D, GREEN))

    print(colorize(BL_D + HZ_D * 68 + BR_D, GREEN))


def print_demo_stats(stats: Dict[str, Any]) -> None:
    """Print beautiful demo completion statistics with P50/P95/P99 latencies."""
    print()
    print(colorize(TL_H + HZ_H * 50 + TR_H, YELLOW))
    print(
        colorize(VT_H, YELLOW)
        + colorize(f"  {GEAR} DEMO STATISTICS", YELLOW, bold=True).ljust(57)
        + colorize(VT_H, YELLOW)
    )
    print(colorize(VT_H + HZ * 50 + VT_H, YELLOW))

    # Basic stats
    stats_lines = [
        f"  {BULLET} Total Turns:        {stats.get('total_turns', 30)}",
        f"  {BULLET} Tool Calls:         {stats.get('tool_calls', 0)}",
        f"  {BULLET} Gap Detections:     {stats.get('gap_detections', 0)}",
        f"  {BULLET} Clarifications:     {stats.get('clarifications', 0)}",
        f"  {BULLET} Background Tasks:   {stats.get('background_tasks', 0)}",
        f"  {BULLET} Crash/Restores:     {stats.get('crash_restores', 1)}",
    ]
    for line in stats_lines:
        print(colorize(VT_H, YELLOW) + line.ljust(50) + colorize(VT_H, YELLOW))

    print(colorize(VT_H + HZ * 50 + VT_H, YELLOW))

    # Latency stats with percentiles
    print(
        colorize(VT_H, YELLOW)
        + colorize(f"  {CLOCK} LATENCY METRICS:", CYAN).ljust(57)
        + colorize(VT_H, YELLOW)
    )
    latency_lines = [
        f"    {BULLET} Avg Latency:      {stats.get('avg_latency_ms', 0)}ms",
        f"    {BULLET} P50 Latency:      {stats.get('p50_latency_ms', 0)}ms",
        f"    {BULLET} P95 Latency:      {stats.get('p95_latency_ms', 0)}ms",
        f"    {BULLET} P99 Latency:      {stats.get('p99_latency_ms', 0)}ms",
    ]
    for line in latency_lines:
        print(colorize(VT_H, YELLOW) + line.ljust(50) + colorize(VT_H, YELLOW))

    print(colorize(VT_H + HZ * 50 + VT_H, YELLOW))

    # SessionState growth
    print(
        colorize(VT_H, YELLOW)
        + colorize(f"  {DATABASE} SESSION STATE:", CYAN).ljust(57)
        + colorize(VT_H, YELLOW)
    )
    state_lines = [
        f"    {BULLET} Initial Size:     {stats.get('initial_bytes', 0)} bytes",
        f"    {BULLET} Final Size:       {stats.get('final_bytes', 0)} bytes",
        f"    {BULLET} Growth:           {stats.get('growth_bytes', 0)} bytes",
        f"    {BULLET} Avg/Turn:         {stats.get('bytes_per_turn', 0)} bytes",
    ]
    for line in state_lines:
        print(colorize(VT_H, YELLOW) + line.ljust(50) + colorize(VT_H, YELLOW))

    print(colorize(BL_H + HZ_H * 50 + BR_H, YELLOW))
    print()

    print(colorize(f"  {CLOCK} Total Duration:     {stats.get('total_duration_s', 0):.1f}s", WHITE))
    print()


def print_demo_complete() -> None:
    """Print demo completion with proper ASCII art."""
    print()

    # Green border
    border = colorize("=" * 70, GREEN, bold=True)
    print(border)
    print()

    # "SUCCESS" ASCII art - properly padded
    success_art = [
        "         ███████╗██╗   ██╗ ██████╗ ██████╗███████╗███████╗███████╗",
        "         ██╔════╝██║   ██║██╔════╝██╔════╝██╔════╝██╔════╝██╔════╝",
        "         ███████╗██║   ██║██║     ██║     █████╗  ███████╗███████╗",
        "         ╚════██║██║   ██║██║     ██║     ██╔══╝  ╚════██║╚════██║",
        "         ███████║╚██████╔╝╚██████╗╚██████╗███████╗███████║███████║",
        "         ╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝╚══════╝╚══════╝╚══════╝",
    ]

    for line in success_art:
        print(colorize(line, GREEN, bold=True))

    print()
    print(colorize("                           DEMO COMPLETE", WHITE, bold=True))
    print()
    print(
        colorize(
            f"       {STAR} Mike is going to have an amazing 50th birthday! {STAR}",
            YELLOW,
            bold=True,
        )
    )
    print()
    print(border)
    print()


def print_k1_coverage_report(coverage: Dict[str, bool]) -> None:
    """Print beautiful K1 architecture coverage report."""
    print()
    print(colorize(TL_H + HZ_H * 50 + TR_H, MAGENTA))
    print(
        colorize(VT_H, MAGENTA)
        + colorize(f"  {STAR} K1 ARCHITECTURE COVERAGE", MAGENTA, bold=True).ljust(57)
        + colorize(VT_H, MAGENTA)
    )
    print(colorize(BL_H + HZ_H * 50 + BR_H, MAGENTA))

    total = len(coverage)
    covered = sum(1 for v in coverage.values() if v)
    pct = (covered / total * 100) if total > 0 else 0

    # Progress bar with Unicode
    bar_width = 30
    filled = int(bar_width * pct / 100)
    bar = colorize(PROG_FULL * filled, GREEN) + colorize(PROG_EMPTY * (bar_width - filled), GRAY)
    print(f"  Overall: {TL}{bar}{TR} {pct:.1f}% ({covered}/{total})")
    print()

    # Component breakdown with Unicode checkmarks
    for component, is_covered in coverage.items():
        icon = colorize(CHECK, GREEN, bold=True) if is_covered else colorize(CROSS, RED)
        print(f"    {icon} {component}")

    print()


def print_walkthrough_explanation(topic: str, explanation: str) -> None:
    """Print beautiful educational walkthrough explanation."""
    print()
    print(colorize(TL_D + HZ_D * 68 + TR_D, BLUE))
    print(
        colorize(VT_D, BLUE)
        + colorize(f"  {STAR} WALKTHROUGH: {topic}", CYAN, bold=True).center(76)
        + colorize(VT_D, BLUE)
    )
    print(colorize(VT_D + HZ * 68 + VT_D, BLUE))

    for line in explanation.strip().split("\n"):
        padded = f"  {line}".ljust(68)
        print(colorize(VT_D, BLUE) + padded + colorize(VT_D, BLUE))

    print(colorize(BL_D + HZ_D * 68 + BR_D, BLUE))
    print()


# ============================================================================
# Interactive Controls
# ============================================================================


def wait_for_key(prompt: str = "Press Enter to continue...") -> None:
    """Wait for user to press Enter."""
    print()
    print(colorize(f"  {ARROW_R} {prompt}", GRAY))
    input()


def prompt_yes_no(question: str) -> bool:
    """Prompt for yes/no response."""
    print()
    response = input(colorize(f"  {question} (y/n): ", YELLOW)).strip().lower()
    return response in ("y", "yes")
