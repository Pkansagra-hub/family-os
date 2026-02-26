"""
poc.k1_poc.demo.display -- Rich terminal display (anniversary demo style).

Full Unicode box-drawing, ANSI color, progress bar display matching
the anniversary_demo output format: turn indicators with progress bars,
FSM state transitions, user/concierge message styling, and system
activity boxes with session ops, tool calls, and state changes.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Console setup
# ---------------------------------------------------------------------------


def setup_unicode_console() -> None:
    """Best-effort UTF-8 console setup for Windows terminals."""
    if sys.platform != "win32":
        return
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

# ---------------------------------------------------------------------------
# Unicode box-drawing characters
# ---------------------------------------------------------------------------

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
BULLET = "\u2022"
STAR = "\u2605"
LIGHTNING = "\u26a1"
WARNING = "\u26a0"
GEAR = "\u2699"
DATABASE = "\u25a3"
CLOCK = "\u231b"

# ---------------------------------------------------------------------------
# ANSI codes
# ---------------------------------------------------------------------------

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
GRAY = "\033[90m"


def colorize(text: str, color: str, *, bold: bool = False, dim: bool = False) -> str:
    prefix = ""
    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    return f"{prefix}{color}{text}{RESET}"


# ---------------------------------------------------------------------------
# ANSI-aware padding helper
# ---------------------------------------------------------------------------

_ANSI_STRIP = re.compile(r"\033\[[0-9;]*m")


def _pad(text: str, width: int = 70) -> str:
    """Pad text to width, accounting for invisible ANSI escape codes."""
    visible = len(_ANSI_STRIP.sub("", text))
    return text + " " * max(0, width - visible)


# ---------------------------------------------------------------------------
# Word-wrap helper
# ---------------------------------------------------------------------------


def _word_wrap(text: str, width: int = 68, indent: str = "  ") -> None:
    """Print word-wrapped text with indent."""
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            print()
            continue
        line = indent
        for word in words:
            if len(line) + len(word) > width:
                print(line)
                line = indent
            line += word + " "
        if line.strip():
            print(line)


# ============================================================================
# Headers and dividers
# ============================================================================


def print_demo_header(
    title: str,
    subtitle: str = "",
    turn_count: str = "",
) -> None:
    """Print the main demo header with ====== borders."""
    print()
    print(colorize("=" * 70, CYAN))
    print(colorize(f"           {title}", CYAN, bold=True))
    if subtitle:
        print(colorize(f"         {subtitle}", YELLOW))
    if turn_count:
        print(colorize(f"           {turn_count}", GRAY))
    print(colorize("=" * 70, CYAN))
    print()


def print_act_header(act_name: str, turns: str = "") -> None:
    """Print an act header with double-border box, centered."""
    width = 70
    print()
    print(colorize(TL_D + HZ_D * width + TR_D, MAGENTA, bold=True))
    _empty = colorize(VT_D, MAGENTA, bold=True) + " " * width + colorize(VT_D, MAGENTA, bold=True)
    print(_empty)
    pad_l = (width - len(act_name)) // 2
    pad_r = width - pad_l - len(act_name)
    print(
        colorize(VT_D, MAGENTA, bold=True)
        + " " * pad_l
        + colorize(act_name, MAGENTA, bold=True)
        + " " * pad_r
        + colorize(VT_D, MAGENTA, bold=True)
    )
    if turns:
        tpad_l = (width - len(turns)) // 2
        tpad_r = width - tpad_l - len(turns)
        print(
            colorize(VT_D, MAGENTA, bold=True)
            + " " * tpad_l
            + colorize(turns, GRAY)
            + " " * tpad_r
            + colorize(VT_D, MAGENTA, bold=True)
        )
    print(_empty)
    print(colorize(BL_D + HZ_D * width + BR_D, MAGENTA, bold=True))
    print()


def print_boot_splash() -> None:
    """Print branded FamilyOS boot splash screen."""
    width = 70

    def _center_line(text: str, color: str, *, bold: bool = False) -> None:
        pad_l = (width - len(text)) // 2
        pad_r = width - pad_l - len(text)
        print(
            colorize(VT_D, CYAN, bold=True)
            + " " * pad_l
            + colorize(text, color, bold=bold)
            + " " * pad_r
            + colorize(VT_D, CYAN, bold=True)
        )

    print()
    print(colorize(TL_D + HZ_D * width + TR_D, CYAN, bold=True))
    _blank = colorize(VT_D, CYAN, bold=True) + " " * width + colorize(VT_D, CYAN, bold=True)
    print(_blank)
    _center_line("F A M I L Y O S", WHITE, bold=True)
    _center_line("Intelligence Kernel v1", CYAN)
    print(_blank)
    _center_line("Cognitive Architecture for Family Life", GRAY)
    print(_blank)
    print(colorize(BL_D + HZ_D * width + BR_D, CYAN, bold=True))
    print()


# ============================================================================
# Turn indicator
# ============================================================================


def print_turn_indicator(turn: int, total: int, act_name: str = "") -> None:
    """Print turn indicator with Unicode box and progress bar."""
    pct = turn / total if total > 0 else 0
    bar_width = 20
    filled = int(bar_width * pct)
    bar = colorize(PROG_FULL * filled, GREEN) + colorize(PROG_EMPTY * (bar_width - filled), GRAY)

    print()
    print(colorize(TL_D + HZ_D * 68 + TR_D, CYAN))
    inner = (
        f"  {ARROW_R} Turn {turn:2d} of {total}  "
        f"{TL}{bar}{TR}  "
        f"{GEAR} {colorize(act_name, YELLOW, bold=True)}"
    )
    print(colorize(VT_D, CYAN) + inner.ljust(90) + colorize(VT_D, CYAN))
    print(colorize(BL_D + HZ_D * 68 + BR_D, CYAN))


# ============================================================================
# Message display
# ============================================================================


# Background color codes
BG_GREEN = "\033[42m"
BG_CYAN = "\033[46m"
BG_BLUE = "\033[44m"


def print_user_message(content: str, member: str = "USER") -> None:
    """Print user message with member name, green border, and content."""
    name = member.upper()
    width = 70
    print()
    print(colorize(TL + HZ * width + TR, GREEN, bold=True))
    # Name label line
    label = f"  {ARROW_R} {name}"
    print(
        colorize(VT, GREEN, bold=True)
        + colorize(label, GREEN, bold=True).ljust(width + 7)
        + colorize(VT, GREEN, bold=True)
    )
    print(colorize(VT + HZ * width + VT, GREEN))
    # Word-wrap content inside the box
    for paragraph in content.split("\n"):
        words = paragraph.split()
        if not words:
            print(colorize(VT, GREEN) + " " * width + colorize(VT, GREEN))
            continue
        line = "  "
        for word in words:
            if len(line) + len(word) > width - 2:
                padded = line.ljust(width)
                print(colorize(VT, GREEN) + colorize(padded, WHITE) + colorize(VT, GREEN))
                line = "  "
            line += word + " "
        if line.strip():
            padded = line.ljust(width)
            print(colorize(VT, GREEN) + colorize(padded, WHITE) + colorize(VT, GREEN))
    print(colorize(BL + HZ * width + BR, GREEN, bold=True))


def print_concierge_message(content: str) -> None:
    """Print concierge/assistant response with bordered box and highlight."""
    width = 70
    print()
    print(colorize(TL_D + HZ_D * width + TR_D, CYAN, bold=True))
    label = f"  {STAR} CONCIERGE"
    print(
        colorize(VT_D, CYAN, bold=True)
        + colorize(label, CYAN, bold=True).ljust(width + 7)
        + colorize(VT_D, CYAN, bold=True)
    )
    print(colorize(VT_D + HZ * width + VT_D, CYAN))
    # Word-wrap content inside the box
    for paragraph in content.split("\n"):
        words = paragraph.split()
        if not words:
            print(colorize(VT_D, CYAN) + " " * width + colorize(VT_D, CYAN))
            continue
        line = "  "
        for word in words:
            if len(line) + len(word) > width - 2:
                padded = line.ljust(width)
                print(colorize(VT_D, CYAN) + colorize(padded, WHITE) + colorize(VT_D, CYAN))
                line = "  "
            line += word + " "
        if line.strip():
            padded = line.ljust(width)
            print(colorize(VT_D, CYAN) + colorize(padded, WHITE) + colorize(VT_D, CYAN))
    print(colorize(BL_D + HZ_D * width + BR_D, CYAN, bold=True))


def print_concierge_message_animated(content: str, delay_per_line: float = 0.04) -> None:
    """Print concierge message with line-by-line streaming reveal.

    Used in story-demo mode for video recording.  Each wrapped content
    line appears with a small delay, producing a streaming effect inside
    the bordered box.
    """
    import time as _time

    width = 70
    print()
    print(colorize(TL_D + HZ_D * width + TR_D, CYAN, bold=True))
    label = f"  {STAR} CONCIERGE"
    print(
        colorize(VT_D, CYAN, bold=True)
        + colorize(label, CYAN, bold=True).ljust(width + 7)
        + colorize(VT_D, CYAN, bold=True)
    )
    print(colorize(VT_D + HZ * width + VT_D, CYAN))
    lines: list[str] = []
    for paragraph in content.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        line = "  "
        for word in words:
            if len(line) + len(word) > width - 2:
                lines.append(line)
                line = "  "
            line += word + " "
        if line.strip():
            lines.append(line)
    for line_text in lines:
        padded = line_text.ljust(width) if line_text else " " * width
        sys.stdout.write(
            colorize(VT_D, CYAN) + colorize(padded, WHITE) + colorize(VT_D, CYAN) + "\n"
        )
        sys.stdout.flush()
        _time.sleep(delay_per_line)
    print(colorize(BL_D + HZ_D * width + BR_D, CYAN, bold=True))


def print_system_message(content: str, severity: str = "info") -> None:
    """Print [SYSTEM] message with color based on severity."""
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
# FSM state transitions
# ============================================================================


def print_fsm_state_transition(
    state_history: List[str],
    intent_type: str = "",
    complexity_tier: str = "",
    classification_ms: int = 0,
) -> None:
    """Print FSM state transitions with visual arrow flow."""
    state_colors = {
        "LISTENING": CYAN,
        "CLARIFYING": MAGENTA,
        "DISPATCHING": BLUE,
        "EXECUTING": GREEN,
        "COMPANIONING": CYAN,
        "PROGRESSING": GREEN,
        "DELIVERING": GREEN,
    }

    print()
    print(colorize(f"  {GEAR} [FSM]", BLUE, bold=True) + " State Transitions:")

    if state_history:
        transitions = []
        for i, state in enumerate(state_history):
            color = state_colors.get(state, GRAY)
            if i == len(state_history) - 1:
                transitions.append(colorize(state, color, bold=True))
            else:
                transitions.append(colorize(state, color, dim=True))
        flow = f" {ARROW_R} ".join(transitions)
        print(f"       {flow}")

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
        print(f"       {BULLET} " + " | ".join(info_parts))


# ============================================================================
# System activity box
# ============================================================================


def print_system_activity(
    turn_num: int,
    session_ops: Optional[List[str]] = None,
    tool_calls: Optional[List[str]] = None,
    state_changes: Optional[Dict[str, Any]] = None,
    bytes_delta: int = 0,
    latency_ms: int = 0,
) -> None:
    """Print system activity box with blue dashboard theme."""
    session_ops = session_ops or []
    tool_calls = tool_calls or []
    state_changes = state_changes or {}
    max_ops = 8

    print()
    print(colorize(TL_H + HZ_H * 68 + TR_H, BLUE))
    hdr = colorize(f"  {GEAR} SYSTEM ACTIVITY - Turn {turn_num}", BLUE, bold=True)
    print(colorize(VT_H, BLUE) + _pad(hdr, 68) + colorize(VT_H, BLUE))
    print(colorize(VT_H + HZ * 68 + VT_H, BLUE))

    has_content = False

    if session_ops:
        has_content = True
        lbl = colorize(f"  {DATABASE} Session Operations:", CYAN)
        print(colorize(VT_H, BLUE) + _pad(lbl, 68) + colorize(VT_H, BLUE))
        display_ops = session_ops[:max_ops]
        for op in display_ops:
            truncated = op[:60] + "..." if len(op) > 60 else op
            item = colorize(f"     {BULLET} {truncated}", CYAN, dim=True)
            print(colorize(VT_H, BLUE) + _pad(item, 68) + colorize(VT_H, BLUE))
        if len(session_ops) > max_ops:
            extra = len(session_ops) - max_ops
            more = colorize(f"     ... +{extra} more", GRAY)
            print(colorize(VT_H, BLUE) + _pad(more, 68) + colorize(VT_H, BLUE))
        print(colorize(VT_H + HZ * 68 + VT_H, BLUE))

    if tool_calls:
        has_content = True
        lbl = colorize(f"  {GEAR} Tool Executions:", MAGENTA)
        print(colorize(VT_H, BLUE) + _pad(lbl, 68) + colorize(VT_H, BLUE))
        for tool in tool_calls:
            item = colorize(f"     {ARROW_R} {tool}", MAGENTA, dim=True)
            print(colorize(VT_H, BLUE) + _pad(item, 68) + colorize(VT_H, BLUE))
        print(colorize(VT_H + HZ * 68 + VT_H, BLUE))

    if not has_content:
        direct = colorize(f"  {LIGHTNING} Direct response (no tool calls)", GREEN)
        print(colorize(VT_H, BLUE) + _pad(direct, 68) + colorize(VT_H, BLUE))
        print(colorize(VT_H + HZ * 68 + VT_H, BLUE))

    if state_changes:
        lbl = colorize(f"  {STAR} State Changes:", YELLOW)
        print(colorize(VT_H, BLUE) + _pad(lbl, 68) + colorize(VT_H, BLUE))
        for key, value in state_changes.items():
            val_str = str(value)[:40] + "..." if len(str(value)) > 40 else str(value)
            item = colorize(f"     {BULLET} {key}: {val_str}", YELLOW, dim=True)
            print(colorize(VT_H, BLUE) + _pad(item, 68) + colorize(VT_H, BLUE))
        print(colorize(VT_H + HZ * 68 + VT_H, BLUE))

    if latency_ms >= 1000:
        latency_str = f"{latency_ms / 1000:.1f}s"
    else:
        latency_str = f"{latency_ms}ms"
    metrics = colorize(
        f"  {CLOCK} {latency_str}  {BULLET}  "
        f"{bytes_delta:+} bytes  {BULLET}  {CHECK} committed",
        GREEN,
        dim=True,
    )
    print(colorize(VT_H, BLUE) + _pad(metrics, 68) + colorize(VT_H, BLUE))
    print(colorize(BL_H + HZ_H * 68 + BR_H, BLUE))


def print_startup_report_visual(
    phases_completed: List[str],
    startup_times: Dict[str, float],
    total_time: float,
    system_ready: bool,
    components: Dict[str, Any],
) -> None:
    """Print styled startup report with per-phase results."""
    width = 70
    _labels = {
        "phase1": "Demo Data",
        "phase2": "Kernel Startup",
        "phase3": "Data Attachment",
        "phase4": "Demo Wiring",
        "phase5": "Health Check",
    }
    _budgets = {"phase1": 1.0, "phase2": 3.0, "phase3": 1.0, "phase4": 1.0, "phase5": 1.0}

    print()
    print(colorize(TL_D + HZ_D * width + TR_D, GREEN, bold=True))
    hdr = colorize(f"  {GEAR} K1 STARTUP REPORT", GREEN, bold=True)
    print(colorize(VT_D, GREEN, bold=True) + _pad(hdr, width) + colorize(VT_D, GREEN, bold=True))
    print(colorize(VT_D + HZ * width + VT_D, GREEN))

    for pk in ["phase1", "phase2", "phase3", "phase4", "phase5"]:
        dur = startup_times.get(pk, 0.0)
        ok = pk in phases_completed
        budget = _budgets[pk]
        num = int(pk[-1])
        lbl = _labels[pk]
        icon = colorize(CHECK, GREEN) if ok else colorize(CROSS, RED)
        dur_c = GREEN if dur <= budget else YELLOW if dur <= budget * 1.5 else RED
        line = (
            f"  {icon} [{num}/5] {lbl:<18s}"
            f"  {colorize(f'{dur:.3f}s', dur_c)}"
            f"  {colorize(f'(budget {budget:.0f}s)', GRAY)}"
        )
        print(
            colorize(VT_D, GREEN, bold=True) + _pad(line, width) + colorize(VT_D, GREEN, bold=True)
        )

    print(colorize(VT_D + HZ * width + VT_D, GREEN))
    r_icon = colorize(CHECK, GREEN) if system_ready else colorize(CROSS, RED)
    r_word = (
        colorize("READY", GREEN, bold=True) if system_ready else colorize("FAILED", RED, bold=True)
    )
    summary = (
        f"  {r_icon} System {r_word}  {BULLET}  " f"Total: {colorize(f'{total_time:.3f}s', CYAN)}"
    )
    print(
        colorize(VT_D, GREEN, bold=True) + _pad(summary, width) + colorize(VT_D, GREEN, bold=True)
    )

    if components:
        print(colorize(VT_D + HZ * width + VT_D, GREEN))
        for cname, cval in components.items():
            cl = colorize(f"     {BULLET} {cname}: {cval}", GRAY)
            print(
                colorize(VT_D, GREEN, bold=True)
                + _pad(cl, width)
                + colorize(VT_D, GREEN, bold=True)
            )

    print(colorize(BL_D + HZ_D * width + BR_D, GREEN, bold=True))
    print()


def print_boot_phase(
    phase_num: int,
    total: int,
    label: str,
    *,
    status: str = "running",
    duration: float = 0.0,
) -> None:
    """Print a single boot phase progress line.

    status: 'running' shows animated dots, 'ok' shows checkmark + duration,
    'fail' shows cross.
    """
    if status == "running":
        dots = colorize("...", YELLOW)
        sys.stdout.write(f"  [{phase_num}/{total}] {label} {dots}")
        sys.stdout.flush()
    elif status == "ok":
        dur_color = GREEN if duration < 1.0 else YELLOW
        sys.stdout.write(
            f"\r  {colorize(CHECK, GREEN)} [{phase_num}/{total}] {label}"
            f"  {colorize(f'{duration:.3f}s', dur_color)}\n"
        )
        sys.stdout.flush()
    elif status == "fail":
        sys.stdout.write(
            f"\r  {colorize(CROSS, RED)} [{phase_num}/{total}] {label}"
            f"  {colorize('FAILED', RED, bold=True)}\n"
        )
        sys.stdout.flush()


# ============================================================================
# Demo stats and completion
# ============================================================================


def print_demo_stats(stats: Dict[str, Any]) -> None:
    """Print demo completion statistics."""
    print()
    print(colorize(TL_H + HZ_H * 50 + TR_H, YELLOW))
    print(
        colorize(VT_H, YELLOW)
        + colorize(f"  {GEAR} DEMO STATISTICS", YELLOW, bold=True).ljust(57)
        + colorize(VT_H, YELLOW)
    )
    print(colorize(VT_H + HZ * 50 + VT_H, YELLOW))

    stat_lines = [
        f"  {BULLET} Total Turns:        {stats.get('total_turns', 0)}",
        f"  {BULLET} Tool Calls:         {stats.get('tool_calls', 0)}",
        f"  {BULLET} FSM Transitions:    {stats.get('fsm_transitions', 0)}",
        f"  {BULLET} State Updates:      {stats.get('state_updates', 0)}",
    ]
    for line in stat_lines:
        print(colorize(VT_H, YELLOW) + line.ljust(50) + colorize(VT_H, YELLOW))

    print(colorize(VT_H + HZ * 50 + VT_H, YELLOW))

    print(
        colorize(VT_H, YELLOW)
        + colorize(f"  {CLOCK} LATENCY METRICS:", CYAN).ljust(57)
        + colorize(VT_H, YELLOW)
    )
    latency_lines = [
        f"    {BULLET} Avg Latency:      {stats.get('avg_latency_ms', 0)}ms",
        f"    {BULLET} P50 Latency:      {stats.get('p50_latency_ms', 0)}ms",
        f"    {BULLET} P95 Latency:      {stats.get('p95_latency_ms', 0)}ms",
    ]
    for line in latency_lines:
        print(colorize(VT_H, YELLOW) + line.ljust(50) + colorize(VT_H, YELLOW))

    print(colorize(BL_H + HZ_H * 50 + BR_H, YELLOW))

    print(
        colorize(
            f"  {CLOCK} Total Duration:     {stats.get('total_duration_s', 0):.1f}s",
            WHITE,
        )
    )
    print()


def print_demo_complete(stats: Optional[Dict[str, Any]] = None) -> None:
    """Print demo completion celebration banner with optional stats."""
    width = 70
    stats = stats or {}

    def _center_line(text: str, color: str, *, bold: bool = False) -> None:
        pad_l = (width - len(text)) // 2
        pad_r = width - pad_l - len(text)
        print(
            colorize(VT_D, GREEN, bold=True)
            + " " * pad_l
            + colorize(text, color, bold=bold)
            + " " * pad_r
            + colorize(VT_D, GREEN, bold=True)
        )

    print()
    print(colorize(TL_D + HZ_D * width + TR_D, GREEN, bold=True))
    _blank = colorize(VT_D, GREEN, bold=True) + " " * width + colorize(VT_D, GREEN, bold=True)
    print(_blank)
    _center_line(f"{CHECK} DEMO COMPLETE {CHECK}", WHITE, bold=True)
    print(_blank)

    if stats:
        turns = stats.get("total_turns", 0)
        duration = stats.get("total_duration_s", 0)
        tools = stats.get("tool_calls", 0)
        if turns:
            _center_line(f"{BULLET} {turns} turns completed", CYAN)
        if tools:
            _center_line(f"{BULLET} {tools} tool executions", CYAN)
        if duration:
            _center_line(f"{BULLET} Total duration: {duration:.1f}s", CYAN)
        print(_blank)

    _center_line("Thank you for watching", GRAY)
    _center_line("github.com/Pkansagra-hub/family-os", GRAY)
    print(_blank)
    print(colorize(BL_D + HZ_D * width + BR_D, GREEN, bold=True))
    print()
