"""Scripted 20-Turn Demo Runner -- Lake Tahoe Family Trip.

Fully automated demo that runs all 20 TRIP_TIMELINE turns with:
  - Real Gemini API calls (function calling)
  - Real SessionState persistence (SQLite)
  - Rich TUI output with FSM transitions, tool calls, timing
  - Press Enter between turns for paced reading

Usage:
    python -m poc.concierge_fsm_poc.run_demo
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from k1.sessionstate import SessionStateFactory, SessionStateManager
from poc.concierge_fsm_poc.fsm.controller import (
    Event,
    FSMController,
    InvalidTransitionError,
    State,
)
from poc.concierge_fsm_poc.fsm.phase1_mock import MockPhase1Classifier, Phase1Result
from poc.concierge_fsm_poc.llm.client import GeminiClient, build_system_prompt
from poc.concierge_fsm_poc.react.events import LoopEvent, LoopEventType
from poc.concierge_fsm_poc.react.loop import ReActLoop, ReActResult
from poc.concierge_fsm_poc.react.scratchpad import Scratchpad
from poc.concierge_fsm_poc.scenarios.trip_timeline import (
    CRISIS_RESPONSE,
    FAMILY_PERSONA,
    TRIP_TIMELINE,
    TurnHint,
)
from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet
from poc.concierge_fsm_poc.tools.read_mock import (
    clear_memory_corpus,
    read_session_state,
    reset_memory_corpus,
)
from poc.concierge_fsm_poc.tools.registry import build_default_registry

logger = logging.getLogger("concierge_fsm.run_demo")
console = Console()

MAX_CLARIFICATION_ROUNDS = 3
_auto_mode = False
_interactive_mode = False
_scenario_persona: dict | None = None  # Set to FAMILY_PERSONA in scenario modes, None in --user


def _pause(prompt: str = "\n  >> Press Enter to continue...\n") -> None:
    """Wait for Enter unless running in --auto mode."""
    if not _auto_mode:
        console.input(prompt)
    else:
        console.print("[dim]  (auto)[/dim]")


# ---------------------------------------------------------------------------
# Story ACT definitions
# ---------------------------------------------------------------------------

ACTS: list[tuple[str, str, list[int]]] = [
    ("ACT 1", "GETTING STARTED", [1, 2, 3]),
    ("ACT 2", "CLARIFICATION LOOPS", [4, 5]),
    ("ACT 3", "INTERRUPT HANDLING", [6, 7, 8, 9]),
    ("ACT 4", "SAFETY & CRISIS", [10, 11]),
    ("ACT 5", "EDGE CASES", [12, 13, 14]),
    ("ACT 6", "DEGRADATION & FAILURE", [15, 16, 17, 18]),
    ("ACT 7", "USER CONTROL & TIMEOUT", [19, 20]),
]


def _get_act(turn_number: int) -> tuple[str, str] | None:
    """Return (act_label, act_title) if this turn starts a new ACT."""
    for label, title, turns in ACTS:
        if turns and turns[0] == turn_number:
            return label, title
    return None


def _get_act_info(turn_number: int) -> tuple[str, str]:
    """Return the current (act_label, act_title) for any turn number."""
    for label, title, turns in ACTS:
        if turn_number in turns:
            return label, title
    return "ACT ?", "UNKNOWN"


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _show_banner(mode: str = "scripted") -> None:
    """Show the welcome banner. Mode-aware: --user shows a generic banner."""
    if mode == "user":
        banner = """
======================================================================
            FAMILYOS CONCIERGE
          Free-Form Chat Mode
======================================================================
"""
        console.print(Text(banner, style="bold cyan"))
        console.print(
            Panel(
                "  Welcome to FamilyOS Concierge!\n"
                "  Chat freely -- ask about anything.\n"
                "\n"
                "  [bold]REAL LLM INTEGRATION:[/bold]\n"
                "    - Real Gemini API calls (function calling)\n"
                "    - Real SessionState persistence (SQLite)\n"
                "    - 8-state FSM with 14 transition types\n"
                "    - 14 tools (6 cognitive, 4 read, 3 action, 1 signal)\n",
                border_style="cyan",
            )
        )
    else:
        banner = """
======================================================================
             THE LAKE TAHOE WEEKEND
           A Family Trip to Remember
             A 20-Turn FamilyOS Demo
======================================================================
"""
        console.print(Text(banner, style="bold cyan"))
        console.print(
            Panel(
                "  Welcome to the Lake Tahoe Family Trip Demo!\n"
                "  This 20-turn demo shows FamilyOS Concierge helping a family\n"
                "  plan a weekend trip to Lake Tahoe.\n"
                "\n"
                "  [bold]REAL LLM INTEGRATION:[/bold]\n"
                "    - Real Gemini API calls (function calling)\n"
                "    - Real SessionState persistence (SQLite)\n"
                "    - 8-state FSM with 14 transition types\n"
                "    - 14 tools (6 cognitive, 4 read, 3 action, 1 signal)\n"
                "\n"
                "  [bold]FLOW COVERAGE:[/bold]\n"
                "    - 20 of 32 documented flows exercised\n"
                "    - Happy paths, clarification, interrupts, crisis\n"
                "    - Safety bands, degradation, user cancel, timeouts\n",
                border_style="cyan",
            )
        )


def _show_act_header(label: str, title: str, turns: list[int]) -> None:
    """Display an ACT separator."""
    console.print()
    console.print(
        Panel(
            f"  {label}: {title}\n" f"  Turns: {turns[0]}-{turns[-1]}",
            style="bold yellow",
            border_style="yellow",
            width=70,
        )
    )


def _progress_bar(turn: int, total: int) -> str:
    """Build a text progress bar."""
    if total <= 0:
        return f"[Turn {turn}]"
    filled = turn - 1
    empty = total - filled
    return f"[{'#' * filled}{'.' * empty}]"


def _show_turn_header(turn_number: int, total: int, hint: TurnHint) -> None:
    """Display the turn header with progress bar."""
    _, act_title = _get_act_info(turn_number)
    bar = _progress_bar(turn_number, total)
    console.print()
    console.print(
        Panel(
            f"  Turn {turn_number:2d} of {total}  {bar}  {act_title}",
            style="bold white on blue",
            width=70,
        )
    )
    console.print(f"  [dim]Flow {hint.flow_id} -- {hint.description}[/dim]")
    console.print(f"  [dim]Expected path: {hint.fsm_path}[/dim]")


def _show_user_message(message: str, scripted: bool = True) -> None:
    """Display the user message."""
    console.print()
    if scripted:
        console.print("[bold]USER[/bold] [dim](scripted):[/dim]")
    else:
        console.print("[bold white]USER:[/bold white]")
    console.print(f"  {message}")


def _show_llm_call(prompt_preview: str, msg_count: int, tool_count: int, tier: str) -> None:
    """Show LLM call details."""
    preview = prompt_preview[:80].replace("\n", " ")
    console.print(
        f"\n  [yellow]LLM CALL[/yellow] gemini\n"
        f'       Prompt: "{preview}..."\n'
        f"       Messages: {msg_count} | Tools available: {tool_count} | Tier: {tier}"
    )


def _show_llm_response(elapsed_ms: int, tool_calls: list[Any], text: str | None) -> None:
    """Show LLM response details."""
    console.print(f"  [green]LLM RESPONSE[/green] ({elapsed_ms}ms)")
    if tool_calls:
        console.print(f"       Tool calls: {len(tool_calls)}")
        for tc in tool_calls:
            name = tc.name if hasattr(tc, "name") else str(tc)
            args_preview = ""
            if hasattr(tc, "arguments"):
                args_str = str(tc.arguments)
                args_preview = args_str[:60] + "..." if len(args_str) > 60 else args_str
            console.print(f"           >> {name}: {args_preview}")
    if text:
        preview = text[:100].replace("\n", " ")
        console.print(f'       Response: "{preview}..."')


def _show_fsm_transitions(transitions: list[tuple[str, str, str]], phase1: Phase1Result) -> None:
    """Display FSM state transitions."""
    if not transitions:
        return
    path = " >> ".join(t[2] for t in transitions)
    first_from = transitions[0][0]
    console.print(
        f"\n  [cyan]FSM[/cyan] State Transitions:\n"
        f"       {first_from} >> {path}\n"
        f"       Intent: {phase1.intent} | Tier: {phase1.tier} | Safety: {phase1.safety_band}"
    )


def _show_concierge_response(response: str) -> None:
    """Display the concierge response."""
    console.print()
    console.print("[bold green]CONCIERGE:[/bold green]")
    # Word-wrap at ~68 chars
    safe = rich_escape(response)
    words = safe.split()
    lines: list[str] = []
    current = "  "
    for w in words:
        if len(current) + len(w) + 1 > 70:
            lines.append(current)
            current = "  " + w
        else:
            current += " " + w if current.strip() else "  " + w
    if current.strip():
        lines.append(current)
    console.print("\n".join(lines))


def _show_system_activity(
    turn_number: int,
    elapsed_ms: int,
    session_ops: list[str],
    tool_execs: list[str],
    bytes_delta: int,
) -> None:
    """Show the system activity panel."""
    lines = [f"  SYSTEM ACTIVITY - Turn {turn_number}"]
    lines.append("  " + "-" * 60)

    if session_ops:
        lines.append("  SessionState Operations:")
        for op in session_ops:
            lines.append(f"     {op}")

    if tool_execs:
        lines.append("  Tool Executions:")
        for tool in tool_execs:
            lines.append(f"     >> {tool}")

    lines.append("  " + "-" * 60)
    committed = "committed" if elapsed_ms > 0 else "skipped"
    lines.append(f"  {elapsed_ms}ms  |  +{bytes_delta} bytes  |  {committed}")

    console.print(
        Panel(
            "\n".join(lines),
            border_style="dim",
            width=70,
        )
    )


# ---------------------------------------------------------------------------
# Session State Snapshot Panel
# ---------------------------------------------------------------------------

_SESSION_STATE_SECTIONS = (
    "beliefs_active",
    "scoreboard",
    "clarifications",
    "affective_now",
    "narrative_active",
)


def _show_session_state_panel(manager: SessionStateManager) -> None:
    """Show a detailed snapshot of all readable SessionState sections.

    Renders a Rich panel with sub-tables for each HOT section so that
    the operator can see exactly what the LLM has written into state.
    """
    outer = Table(show_header=False, show_edge=False, padding=(0, 1), expand=True)
    outer.add_column(ratio=1)

    for sect_name in _SESSION_STATE_SECTIONS:
        try:
            result = read_session_state(manager, section=sect_name)
            data = result.get("data", {})
        except Exception as exc:
            outer.add_row(Text(f"  {sect_name}: (error: {exc})", style="dim red"))
            continue

        sect_table = Table(
            show_header=False,
            show_edge=False,
            padding=(0, 0, 0, 2),
            expand=True,
        )
        sect_table.add_column("Key", style="dim", width=28, no_wrap=True)
        sect_table.add_column("Value", style="white")

        row_count = 0

        if sect_name == "beliefs_active":
            facts = data.get("facts", [])
            entities = data.get("entities", [])
            sect_table.add_row("fact_count", str(data.get("fact_count", 0)))
            sect_table.add_row("entity_count", str(data.get("entity_count", 0)))
            row_count += 2
            for f in facts:
                subj = f.get("subject", "?")
                pred = f.get("predicate", "?")
                obj_ = f.get("object", "?")
                conf = f.get("confidence", 1.0)
                pinned = " [pinned]" if f.get("is_pinned") else ""
                sect_table.add_row(
                    f"  {subj}",
                    Text(f"{pred} -> {obj_} ({conf:.0%}){pinned}"),
                )
                row_count += 1
            for e in entities:
                sect_table.add_row(
                    f"  entity:{e.get('type', '?')}",
                    Text(e.get("name", "?")),
                )
                row_count += 1
            mt = data.get("mentioned_time")
            if mt:
                sect_table.add_row("  mentioned_time", Text(str(mt)))
                row_count += 1
            ml = data.get("mentioned_location")
            if ml:
                sect_table.add_row("  mentioned_location", Text(str(ml)))
                row_count += 1

        elif sect_name == "scoreboard":
            referents = data.get("referents", [])
            topics = data.get("topics", [])
            questions = data.get("open_questions", [])
            raw_intent = data.get("user_intent", "")
            # user_intent may be a tuple (intent_str, confidence)
            if isinstance(raw_intent, tuple):
                intent_str, intent_conf = raw_intent
                if intent_str:
                    sect_table.add_row(
                        "user_intent",
                        Text(f"{intent_str} ({intent_conf:.0%})"),
                    )
                    row_count += 1
            elif raw_intent:
                sect_table.add_row("user_intent", Text(str(raw_intent)))
                row_count += 1
            sect_table.add_row("referent_count", str(len(referents)))
            row_count += 1
            for r in referents:
                sect_table.add_row(
                    f"  ref:{r.get('entity_type', '?')}",
                    Text(f"{r.get('text', '?')} (salience={r.get('salience', 0):.1f})"),
                )
                row_count += 1
            for t in topics:
                primary = " *primary*" if t.get("is_primary") else ""
                sect_table.add_row(
                    "  topic",
                    Text(f"{t.get('name', '?')} (salience={t.get('salience', 0):.1f}){primary}"),
                )
                row_count += 1
            for q in questions:
                sect_table.add_row(
                    "  qud",
                    Text(f"{q.get('status', '?')}: {q.get('text', '?')}"),
                )
                row_count += 1

        elif sect_name == "clarifications":
            pending = data.get("pending", [])
            resolved = data.get("recently_resolved", [])
            sect_table.add_row("pending_count", str(data.get("pending_count", 0)))
            sect_table.add_row("is_blocked", str(data.get("is_blocked", False)))
            row_count += 2
            for p in pending:
                sect_table.add_row(
                    "  pending",
                    Text(f"{p.get('question', '?')} ({p.get('priority', '?')})"),
                )
                row_count += 1
            for r in resolved:
                sect_table.add_row(
                    "  resolved",
                    Text(f"{r.get('question', '?')} -> {r.get('answer', '?')}"),
                )
                row_count += 1

        elif sect_name == "affective_now":
            for key in (
                "current_emotion",
                "intensity",
                "valence",
                "arousal",
                "dominance",
                "trajectory",
                "confidence",
                "source",
                "empathy_needed",
                "celebration_appropriate",
            ):
                val = data.get(key, "")
                if isinstance(val, float):
                    val = f"{val:.2f}"
                elif isinstance(val, bool):
                    val = str(val)
                sect_table.add_row(f"  {key}", str(val))
                row_count += 1

        elif sect_name == "narrative_active":
            arc_pos = data.get("arc_position", "EXPOSITION")
            arc_prog = data.get("arc_progress", 0.0)
            sect_table.add_row("arc_position", str(arc_pos))
            sect_table.add_row("arc_progress", f"{arc_prog:.0%}")
            row_count += 2
            threads = data.get("threads", [])
            for t in threads:
                goal_met = " (DONE)" if t.get("is_goal_met") else ""
                sect_table.add_row(
                    "  thread",
                    Text(f"{t.get('title', '?')} ({t.get('state', '?')}){goal_met}"),
                )
                row_count += 1
            if not threads:
                sect_table.add_row("  threads", Text("(none)", style="dim"))
                row_count += 1

        else:
            # Generic fallback: dump all keys
            for k, v in data.items():
                sect_table.add_row(f"  {k}", Text(str(v)[:60]))
                row_count += 1

        if row_count == 0:
            sect_table.add_row("", Text("(empty)", style="dim"))

        header_text = Text(f"  {sect_name}", style="bold cyan")
        outer.add_row(header_text)
        outer.add_row(sect_table)
        outer.add_row(Text(""))  # spacer

    console.print(
        Panel(
            outer,
            title="[bold yellow]Session State Snapshot[/bold yellow]",
            border_style="yellow",
            width=72,
        )
    )


def _show_session_summary(
    fsm: FSMController,
    manager: SessionStateManager,
    total_turns: int,
    total_ms: int,
    llm_calls: int,
    tokens_in: int,
    tokens_out: int,
) -> None:
    """Show final session summary."""
    console.print()
    console.print(
        Panel(
            "======================================================================\n"
            "                    DEMO COMPLETE\n"
            "======================================================================",
            style="bold green",
            width=70,
        )
    )

    tbl = Table(title="Session Summary", show_lines=True, width=70)
    tbl.add_column("Metric", style="cyan", width=30)
    tbl.add_column("Value", style="white", width=36)
    tbl.add_row("Turns completed", str(total_turns))
    tbl.add_row("FSM transitions", str(len(fsm.history)))
    tbl.add_row("LLM calls", str(llm_calls))
    tbl.add_row("Total tokens (in)", f"{tokens_in:,}")
    tbl.add_row("Total tokens (out)", f"{tokens_out:,}")
    tbl.add_row("Total time", f"{total_ms / 1000:.1f}s")

    # State coverage
    states_visited = set()
    transitions_fired = set()
    for from_s, evt, to_s in fsm.history:
        states_visited.add(from_s)
        states_visited.add(to_s)
        if evt == Event.INTERRUPT_DETECTED:
            transitions_fired.add("T13")
        else:
            transitions_fired.add(_label_transition(from_s, evt, to_s))
    tbl.add_row("States visited", f"{len(states_visited)}/8")
    tbl.add_row("Transition types fired", f"{len(transitions_fired)}/14")

    # Flow coverage
    exercised = {h.flow_id for h in TRIP_TIMELINE}
    tbl.add_row("Flows exercised", f"{len(exercised)}/20")

    console.print(tbl)

    # SessionState final snapshot
    try:
        overview = read_session_state(manager, section=None)
        data = overview.get("data", {})
        snap_tbl = Table(title="Final SessionState", show_lines=True, width=70)
        snap_tbl.add_column("Section", style="cyan", width=20)
        snap_tbl.add_column("Details", style="white", width=46)
        for sect_name, sect_data in data.items():
            if isinstance(sect_data, dict):
                details = ", ".join(f"{k}={v}" for k, v in sect_data.items() if k != "error")
            else:
                details = str(sect_data)
            snap_tbl.add_row(sect_name, details[:46] or "(empty)")
        console.print(snap_tbl)
    except Exception:
        pass


def _label_transition(from_state: State, event: Event, to_state: State) -> str:
    """Map a transition triple to its label (T1-T14)."""
    mapping = {
        (State.LISTENING, Event.MESSAGE_RECEIVED, State.ACKING): "T1",
        (State.ACKING, Event.CRISIS_DETECTED, State.DELIVERING): "T2",
        (State.ACKING, Event.PHASE1_COMPLETE, State.DISPATCHING): "T3",
        (State.ACKING, Event.GAPS_DETECTED, State.CLARIFYING): "T4",
        (State.CLARIFYING, Event.CLARIFICATION_RECEIVED, State.ACKING): "T5",
        (State.CLARIFYING, Event.MAX_ROUNDS_REACHED, State.DISPATCHING): "T6",
        (State.DISPATCHING, Event.PRELIMINARY_ACK_SENT, State.COMPANIONING): "T7",
        (State.DISPATCHING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T8",
        (State.COMPANIONING, Event.PROGRESS_RECEIVED, State.PROGRESSING): "T9",
        (State.COMPANIONING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T10",
        (State.PROGRESSING, Event.DISPATCH_COMPLETE, State.DELIVERING): "T11",
        (State.DELIVERING, Event.RESPONSE_DELIVERED, State.LISTENING): "T12",
        (State.INTERRUPT_HANDLING, Event.INTERRUPT_HANDLED, State.ACKING): "T14",
    }
    return mapping.get((from_state, event, to_state), "?")


# ---------------------------------------------------------------------------
# SessionState write helpers (reused from demo.py)
# ---------------------------------------------------------------------------


def _phase1_system_writes(
    manager: SessionStateManager,
    phase1: Phase1Result,
    turn_number: int,
) -> list[str]:
    """Write Phase 1 outputs into SessionState. Returns list of ops for display."""
    ops: list[str] = []

    # Control section uses set_flow_phase / set_primary_domain — no generic update.
    # Record intent for display but skip unsupported mutate.
    try:
        sec = manager.get_section("control")
        sec.set_flow_phase(sec.FlowPhase.TURN_ACTIVE if hasattr(sec, "FlowPhase") else 1)
    except Exception:
        pass
    ops.append("control.set(turn, tier, safety)")

    manager.mutate(
        "affective_now",
        "update",
        {
            "emotion": phase1.emotion,
            "intensity": 0.5,
            "valence": 0.0,
            "source": f"phase1:{phase1.intent}",
            "turn_number": turn_number,
        },
    )
    ops.append(f"affective_now.update(emotion={phase1.emotion})")

    for entity_key, entity_value in phase1.entities.items():
        manager.mutate(
            "scoreboard",
            "add_referent",
            {
                "text": entity_value,
                "entity_id": f"p1-{entity_key}",
                "entity_type": entity_key,
                "salience": phase1.confidence,
            },
        )
        ops.append(f"scoreboard.add_referent({entity_value})")

    return ops


def _phase3_turn_logger(
    manager: SessionStateManager,
    fsm: FSMController,
    turn_number: int,
    user_message: str,
    final_response: str,
    result: ReActResult,
) -> list[str]:
    """Log the completed turn to SessionState. Returns list of ops."""
    ops: list[str] = []

    # history_active.append(user_message, assistant_response, **kwargs)
    # turn_number is auto-assigned, fsm_path and timestamp are not valid kwargs.
    manager.mutate(
        "history_active",
        "append",
        {
            "user_message": user_message,
            "assistant_response": final_response,
        },
    )
    ops.append(f"history.append(user_msg, len={len(user_message)})")
    ops.append(f"history.append(assistant_msg, len={len(final_response)})")

    # Meta section has no generic update(); touch is enough for the POC.
    try:
        sec = manager.get_section("meta")
        if hasattr(sec, "touch"):
            sec.touch()
    except Exception:
        pass
    ops.append("meta.touch(turn_end)")

    return ops


# ---------------------------------------------------------------------------
# Interrupt constraint binding
# ---------------------------------------------------------------------------


def _bind_interrupt_to_beliefs(
    manager: SessionStateManager,
    interrupt_message: str,
    turn_number: int,
) -> None:
    """Commit an interrupt message to beliefs_active so the LLM sees it.

    Without this, the LLM has no evidence the user changed their mind
    (e.g. "Actually make it vegetarian") and continues generating
    responses based on the original request.

    Uses the ``add_fact`` operation (SVO format) which is the only
    valid mutation for beliefs_active accepted by MutationGuard.
    """
    try:
        manager.mutate(
            "beliefs_active",
            "add_fact",
            {
                "subject": "user",
                "predicate": "interrupted_with",
                "obj": interrupt_message,
                "confidence": 1.0,
                "source": f"interrupt_t{turn_number}",
            },
        )
    except Exception:
        pass  # POC: best-effort binding


def _clear_special_flags(
    classifier: MockPhase1Classifier,
    hint: TurnHint,
) -> None:
    """Reset classifier special flags set by this turn's hint.

    Must be called before ANY early return from ``_run_turn`` so flags
    do not leak into subsequent turns.
    """
    if hint.special_flags:
        for flag in hint.special_flags:
            if hasattr(classifier, flag):
                if flag == "raise_on_next":
                    classifier.raise_on_next = False
                elif flag == "force_cb_open":
                    classifier.force_cb_open = False
                elif flag == "watchdog_timeout_ms":
                    classifier.watchdog_timeout_ms = 0


# ---------------------------------------------------------------------------
# Live ReAct Loop Display (Rich Live panel)
# ---------------------------------------------------------------------------


class LiveLoopDisplay:
    """Real-time display of ReAct loop activity using Rich Live.

    Implements ``LoopEventHandler`` to receive events from the loop and
    renders them as a continuously updating Rich Panel showing:
    - Status bar with iteration, elapsed time, tools, findings
    - FSM state badge and active tool
    - Reasoning chain connecting thoughts to tool calls per iteration
    - Recent findings
    - Streaming text preview
    """

    def __init__(self) -> None:
        from collections import deque

        self._iteration: int = 0
        self._current_action: str = "Initializing..."
        self._events_log: deque[tuple[str, str]] = deque(maxlen=8)
        self._streaming_text: list[str] = []
        self._tool_active: str | None = None
        self._findings_count: int = 0
        self._tools_used: int = 0
        self._live: Live | None = None
        self._start_time: float = time.time()
        self._fsm_state: str = "LISTENING"
        self._recent_findings: deque[tuple[str, str]] = deque(maxlen=3)
        self._elapsed_s: float = 0.0

        # -- Reasoning chain: tracks thought+tools per iteration -----------
        # Each entry: {iteration, thought, tools: [(name, ok, summary)], cache_hits: [name]}
        self._chain: list[dict[str, Any]] = []
        self._cycle_warnings: list[str] = []

    def attach_live(self, live: Live) -> None:
        """Attach the Rich Live instance for forced refreshes."""
        self._live = live

    def on_event(self, event: LoopEvent) -> None:
        """Handle a loop event -- update internal state and refresh display."""
        t = event.type
        d = event.data

        # Update elapsed time on every event
        self._elapsed_s = time.time() - self._start_time

        if t == LoopEventType.ITERATION_START:
            self._iteration = d.get("iteration", 0)
            self._current_action = "Thinking..."
            self._log("dim", f"--- Iteration {self._iteration} ---")
            # Start a new reasoning chain entry for this iteration
            self._chain.append(
                {
                    "iteration": self._iteration,
                    "thought": "",
                    "tools": [],
                    "cache_hits": [],
                }
            )

        elif t == LoopEventType.LLM_CALL_START:
            mc = d.get("message_count", 0)
            tc = d.get("tool_count", 0)
            self._current_action = f"Calling LLM ({mc} msgs, {tc} tools)..."
            self._log("yellow", f"~ LLM call: {mc} messages, {tc} tools available")

        elif t == LoopEventType.LLM_CALL_END:
            ti = d.get("tokens_in", 0)
            to = d.get("tokens_out", 0)
            has_tc = d.get("has_tool_calls", False)
            label = "tool calls" if has_tc else "text response"
            self._current_action = f"Processing {label}..."
            self._log("green", f"LLM responded: {ti} in / {to} out -> {label}")

        elif t == LoopEventType.TEXT_DELTA:
            text = d.get("text", "")
            self._streaming_text.append(text)

        elif t == LoopEventType.TOOL_CALL_START:
            name = d.get("tool_name", "?")
            self._tool_active = name
            self._tools_used += 1
            self._current_action = f"Calling {name}..."
            args_preview = str(d.get("arguments", {}))
            if len(args_preview) > 60:
                args_preview = args_preview[:57] + "..."
            self._log("cyan", f">> {name}({args_preview})")

        elif t == LoopEventType.TOOL_CALL_END:
            name = d.get("tool_name", "?")
            ok = d.get("success", False)
            summary = d.get("summary", "")[:80]
            marker = "[ok]" if ok else "[x]"
            status = "[green]OK[/green]" if ok else "[red]FAIL[/red]"
            self._tool_active = None
            self._log("white", f"{marker} {name} -> {status}: {summary}")
            # Record in reasoning chain
            if self._chain:
                self._chain[-1]["tools"].append((name, ok, summary[:60]))

        elif t == LoopEventType.FINDING_EXTRACTED:
            key = d.get("key", "?")
            value = str(d.get("value", ""))[:60]
            self._findings_count += 1
            self._recent_findings.append((key, value))
            self._log("magenta", f"* Learned: {key} = {value}")

        elif t == LoopEventType.FSM_TRANSITION:
            from_s = d.get("from_state", "?")
            evt = d.get("event", "?")
            to_s = d.get("to_state", "?")
            self._fsm_state = to_s
            self._log("blue", f"   FSM: {from_s} --{evt}--> {to_s}")

        elif t == LoopEventType.COMPACTION:
            slen = d.get("summary_len", 0)
            self._log("yellow", f"   Compacted messages ({slen} chars)")

        elif t == LoopEventType.BUDGET_WARNING:
            resource = d.get("resource", "?")
            used = d.get("used", 0)
            limit = d.get("limit", 0)
            self._log("red", f"!! BUDGET: {resource} {used}/{limit}")

        elif t == LoopEventType.LOOP_COMPLETE:
            iters = d.get("iterations", 0)
            tools = d.get("tools_used", 0)
            exhausted = d.get("budget_exhausted", False)
            suffix = " (budget exhausted)" if exhausted else ""
            self._current_action = "Complete"
            self._log("bold green", f"Loop complete: {iters} iterations, {tools} tools{suffix}")

        elif t == LoopEventType.THOUGHT:
            thought = d.get("text", "")[:120]
            it = d.get("iteration", "?")
            self._log("italic dim", f"[think-{it}] {thought}")
            # Record in reasoning chain
            if self._chain:
                self._chain[-1]["thought"] = d.get("text", "")[:200]

        elif t == LoopEventType.CYCLE_DETECTED:
            pattern = d.get("pattern", [])
            self._log("bold red", f"!! CYCLE: {' -> '.join(pattern)} (breaking)")
            self._cycle_warnings.append(" -> ".join(pattern))

        elif t == LoopEventType.TOOL_CACHE_HIT:
            name = d.get("tool_name", "?")
            self._log("dim", f"   [cache] {name} (reused)")
            # Record in reasoning chain
            if self._chain:
                self._chain[-1]["cache_hits"].append(name)

        # Force a Live refresh for significant events only.
        # TEXT_DELTA events arrive dozens of times per LLM call;
        # forcing a refresh on each one overwhelms terminals that
        # don't support cursor-control (causing the panel header
        # to be printed repeatedly).  Rich Live already auto-
        # refreshes at the configured rate (10 fps) so text deltas
        # will appear on the next scheduled frame.
        if self._live is not None and t != LoopEventType.TEXT_DELTA:
            self._live.refresh()

    def _log(self, style: str, message: str) -> None:
        """Add a styled message to the event log."""
        self._events_log.append((style, message))

    def __rich__(self) -> Panel:
        """Build a multi-section Rich Table layout for the Live display.

        Sections:
        1. Status bar     -- spinner, iteration, elapsed, tools, findings
        2. State row      -- FSM state badge (colored), active tool
        3. Reasoning chain -- thought -> tool calls per iteration (last 3)
        4. Recent findings -- last 3 key=value pairs
        5. Stream         -- streaming text preview with blinking cursor
        """
        from rich import box

        table = Table(
            show_header=False,
            box=box.ROUNDED,
            width=68,
            pad_edge=False,
        )
        table.add_column(ratio=1)

        # -- Row 1: Status bar -------------------------------------------------
        status = Text()
        spinner_char = ["|", "/", "-", "\\"][self._iteration % 4]
        if self._current_action != "Complete":
            status.append(f" [{spinner_char}] ", style="bold yellow")
        else:
            status.append(" [done] ", style="bold green")
        status.append(f"Iteration {self._iteration}", style="bold")
        elapsed = f"{self._elapsed_s:.1f}s"
        status.append(f"  |  {elapsed}", style="dim")
        status.append(f"  |  Tools: {self._tools_used}", style="dim")
        status.append(f"  |  Found: {self._findings_count}", style="dim")
        table.add_row(status)

        # -- Row 2: FSM state + active tool ------------------------------------
        state_row = Text()
        fsm_colors = {
            "LISTENING": "green",
            "ACKING": "yellow",
            "DISPATCHING": "cyan",
            "COMPANIONING": "magenta",
            "PROGRESSING": "blue",
            "CLARIFYING": "red",
            "DELIVERING": "bold green",
            "INTERRUPT_HANDLING": "bold red",
        }
        color = fsm_colors.get(self._fsm_state, "white")
        state_row.append(" FSM: ", style="dim")
        state_row.append(self._fsm_state, style=f"bold {color}")
        state_row.append("   |   ", style="dim")
        if self._tool_active:
            state_row.append(f"Tool: {self._tool_active}", style="cyan")
        else:
            state_row.append("Tool: Idle", style="dim")
        table.add_row(state_row)

        # -- Row 3: Reasoning Chain (last 3 iterations) ------------------------
        chain_text = Text()
        chain_text.append(" Reasoning Chain:\n", style="bold white")
        visible_chain = self._chain[-3:] if self._chain else []
        if visible_chain:
            for i, step in enumerate(visible_chain):
                it_num = step["iteration"]
                thought = step.get("thought", "")
                tools = step.get("tools", [])
                cache_hits = step.get("cache_hits", [])
                is_last = i == len(visible_chain) - 1
                connector = "+" if is_last else "|"

                # Iteration header
                chain_text.append(f"   {connector}-- ", style="dim")
                chain_text.append(f"Step {it_num}", style="bold cyan")
                chain_text.append("\n")

                # Thought bubble (if present)
                if thought:
                    preview = thought[:100]
                    if len(thought) > 100:
                        preview += "..."
                    chain_text.append(f"   {connector}   ", style="dim")
                    chain_text.append('"', style="italic yellow")
                    chain_text.append(preview, style="italic yellow")
                    chain_text.append('"\n', style="italic yellow")

                # Tool calls with status indicators
                for tool_name, ok, summary in tools:
                    icon = "[green]>[/green]" if ok else "[red]x[/red]"
                    chain_text.append(f"   {connector}   ", style="dim")
                    # Can't use markup in Text.append, use plain style
                    if ok:
                        chain_text.append("> ", style="green")
                    else:
                        chain_text.append("x ", style="red")
                    chain_text.append(tool_name, style="cyan")
                    if summary:
                        chain_text.append(f"  {summary}", style="dim")
                    chain_text.append("\n")

                # Cache hits
                for cached_name in cache_hits:
                    chain_text.append(f"   {connector}   ", style="dim")
                    chain_text.append("~ ", style="dim")
                    chain_text.append(cached_name, style="dim italic")
                    chain_text.append(" (cached)", style="dim italic")
                    chain_text.append("\n")

            # Cycle warning banner
            if self._cycle_warnings:
                chain_text.append("   !! ", style="bold red")
                chain_text.append(f"CYCLE DETECTED: {self._cycle_warnings[-1]}", style="bold red")
                chain_text.append("\n")
        else:
            chain_text.append("   (waiting for first iteration)\n", style="dim")
        table.add_row(chain_text)

        # -- Row 4: Recent findings --------------------------------------------
        findings_text = Text()
        findings_text.append(" Findings:\n", style="bold magenta")
        if self._recent_findings:
            for key, value in self._recent_findings:
                findings_text.append(f"   {key}", style="magenta")
                findings_text.append(" = ", style="dim")
                findings_text.append(f"{value}\n", style="white")
        else:
            findings_text.append("   (none yet)\n", style="dim")
        table.add_row(findings_text)

        # -- Row 5: Streaming text preview -------------------------------------
        if self._streaming_text:
            full = "".join(self._streaming_text)
            preview = full[-200:] if len(full) > 200 else full
            if len(full) > 200:
                preview = "..." + preview
            stream_text = Text()
            stream_text.append(" Streaming: ", style="bold cyan")
            stream_text.append(preview, style="white")
            stream_text.append("_", style="bold blink")
            table.add_row(stream_text)

        return Panel(
            table,
            title="[bold cyan] ReAct Live [/bold cyan]",
            border_style="cyan",
            width=72,
        )


# ---------------------------------------------------------------------------
# Typewriter response display
# ---------------------------------------------------------------------------


def _show_concierge_response_typewriter(response: str) -> None:
    """Display the concierge response with a typewriter effect."""
    console.print()
    console.print("[bold green]CONCIERGE:[/bold green]")

    # Word-wrap and display word by word
    words = response.split()
    display_text = Text("  ")
    current_line_len = 2

    with Live(display_text, console=console, refresh_per_second=30) as live:
        for word in words:
            if current_line_len + len(word) + 1 > 70:
                display_text.append("\n  ")
                current_line_len = 2
            if current_line_len > 2:
                display_text.append(" ")
                current_line_len += 1
            display_text.append(word)
            current_line_len += len(word)
            live.refresh()
            time.sleep(0.025)


# ---------------------------------------------------------------------------
# Clarification loop (scripted answers)
# ---------------------------------------------------------------------------


async def _run_clarification(
    manager: SessionStateManager,
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    original_message: str,
    phase1: Phase1Result,
    hint: TurnHint,
    llm: GeminiClient | None = None,
) -> tuple[Phase1Result, list[str]]:
    """Run clarification rounds.

    In interactive mode (``_interactive_mode``), prompts the user for
    answers.  In scripted mode, uses pre-scripted answers from the hint.

    When *llm* is provided the concierge question is generated by the
    LLM for a warmer, more natural phrasing.  Falls back to a raw gap
    list when the LLM call fails or is not supplied.

    Returns (final_phase1, session_ops_list).
    """
    current_phase1 = phase1
    session_ops: list[str] = []
    scripted_idx = 0
    # Collect all clarification answers so they can be injected into context
    _clarification_answers: list[tuple[str, str]] = []

    for round_num in range(1, MAX_CLARIFICATION_ROUNDS + 1):
        gaps_text = ", ".join(current_phase1.gaps)
        console.print(
            f"\n  [cyan]CLARIFICATION[/cyan] Round {round_num}/{MAX_CLARIFICATION_ROUNDS}"
        )
        console.print(f"  [dim](gaps: {gaps_text})[/dim]")

        # Generate a natural clarification question via LLM (or fallback)
        if llm is not None:
            try:
                question = await llm.generate_clarification_question(
                    original_message,
                    current_phase1.gaps,
                    current_phase1.intent,
                    prior_answers=_clarification_answers,
                )
            except Exception:
                question = f"Could you clarify: {gaps_text}?"
        else:
            question = f"Could you clarify: {gaps_text}?"

        if _interactive_mode:
            # Interactive: prompt user for clarification answer
            q_line = Text("  CONCIERGE: ", style="cyan")
            q_line.append(question)
            console.print()
            console.print(q_line)
            answer = console.input("  Your answer: ").strip()
            if not answer:
                answer = "no additional info"
            console.print(f"  [bold white]USER:[/bold white] {answer}")
        else:
            # Scripted: use pre-scripted answer from hint
            q_line = Text("  CONCIERGE: ", style="cyan")
            q_line.append(question)
            console.print(q_line)
            if scripted_idx < len(hint.clarification_answers):
                answer = hint.clarification_answers[scripted_idx]
                scripted_idx += 1
            else:
                answer = "no additional info"
            console.print(f"  [dim]USER (scripted): {answer}[/dim]")

        # Check interrupt during clarification
        if hint.interrupt_message and round_num > 1:
            # F18: interrupt during round 2
            console.print(
                f"\n  [red]INTERRUPT[/red] during clarification: " f'"{hint.interrupt_message}"'
            )
            fsm.transition(Event.INTERRUPT_DETECTED)
            session_ops.append("FSM: CLARIFYING -> INTERRUPT_HANDLING")
            fsm.transition(Event.INTERRUPT_HANDLED)
            session_ops.append("FSM: INTERRUPT_HANDLING -> ACKING")

            # Cancel hard-stop: if the interrupt IS a cancellation,
            # mark as cancelled and return without reclassifying.
            _CANCEL_KEYWORDS = frozenset(
                {
                    "cancel",
                    "stop",
                    "never mind",
                    "nevermind",
                    "forget it",
                    "drop it",
                    "skip it",
                    "abort",
                }
            )
            _int_lower = hint.interrupt_message.lower()
            if any(kw in _int_lower for kw in _CANCEL_KEYWORDS):
                console.print("\n  [red]CANCEL DETECTED[/red] during clarification -- hard stop")
                # Return a synthetic Phase1Result flagged as cancelled
                current_phase1 = classifier.classify_with_fallback(
                    hint.interrupt_message, "cancelled"
                )
                current_phase1._cancelled = True
                return current_phase1, session_ops

            # Bind interrupt to beliefs so LLM sees the constraint
            _bind_interrupt_to_beliefs(manager, hint.interrupt_message, 0)
            # Reclassify with interrupt message
            current_phase1 = classifier.classify_with_fallback(
                hint.interrupt_message, "interrupted"
            )
            # Tag so _run_turn uses interrupt message as the LLM query
            current_phase1._interrupt_message = hint.interrupt_message
            return current_phase1, session_ops

        # CLARIFICATION_RECEIVED -> ACKING
        fsm.transition(Event.CLARIFICATION_RECEIVED)
        session_ops.append(f"clarification.resolve(round={round_num}, answer={answer})")
        _clarification_answers.append((f"round_{round_num}", answer))

        # Re-classify with enriched context
        enriched = f"{original_message} | clarification: {answer}"
        current_phase1 = classifier.classify_with_fallback(enriched, f"round:{round_num}")

        if not current_phase1.gaps:
            console.print("  [green]Gaps resolved.[/green]")
            current_phase1._clarification_context = _clarification_answers
            return current_phase1, session_ops

        if round_num < MAX_CLARIFICATION_ROUNDS:
            # Still have gaps, go back to CLARIFYING for next round
            fsm.transition(Event.GAPS_DETECTED)
        else:
            # Last round, gaps remain -- fire MAX_ROUNDS_REACHED from ACKING
            # But T6 requires CLARIFYING, so re-enter CLARIFYING first
            fsm.transition(Event.GAPS_DETECTED)
            console.print("  [yellow]Max clarification rounds reached. Force-proceeding.[/yellow]")
            fsm.transition(Event.MAX_ROUNDS_REACHED)
            session_ops.append("FSM: MAX_ROUNDS_REACHED -> DISPATCHING (force-proceed)")
            current_phase1._clarification_context = _clarification_answers
            return current_phase1, session_ops

    # Fallback (should not reach here normally)
    console.print("  [yellow]Max clarification rounds reached. Force-proceeding.[/yellow]")
    fsm.transition(Event.MAX_ROUNDS_REACHED)
    session_ops.append("FSM: MAX_ROUNDS_REACHED -> DISPATCHING (force-proceed)")
    current_phase1._clarification_context = _clarification_answers
    return current_phase1, session_ops


# ---------------------------------------------------------------------------
# Single turn execution
# ---------------------------------------------------------------------------


async def _run_turn(
    turn_number: int,
    total_turns: int,
    hint: TurnHint,
    manager: SessionStateManager,
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    registry: Any,
    llm: GeminiClient,
    override_message: str | None = None,
) -> dict[str, Any]:
    """Execute a single turn. Returns metrics dict.

    Parameters
    ----------
    override_message:
        When set, replaces ``hint.suggested_message`` for classification
        and LLM input. Used by --user and --guided interactive modes.
    """
    turn_start = time.time()
    session_ops: list[str] = []
    tool_execs: list[str] = []
    user_message = override_message or hint.suggested_message
    is_scripted = override_message is None

    # Show turn header + user message
    _show_turn_header(turn_number, total_turns, hint)
    _show_user_message(user_message, scripted=is_scripted)

    # Apply special flags
    if hint.special_flags:
        for flag, value in hint.special_flags.items():
            if hasattr(classifier, flag):
                setattr(classifier, flag, value)
                console.print(f"  [dim](flag: {flag}={value})[/dim]")

    # Reset per-turn state
    scratchpad = Scratchpad()

    # FSM: LISTENING -> ACKING
    try:
        fsm.transition(Event.MESSAGE_RECEIVED)
    except InvalidTransitionError:
        fsm.reset()
        fsm.transition(Event.MESSAGE_RECEIVED)

    # Phase 1: Classify
    degraded = False
    classify_start = time.time()
    try:
        phase1 = classifier.classify_with_fallback(user_message, f"turn:{turn_number}")
        degraded = phase1.classifier_degraded
    except Exception as exc:
        console.print(f"  [red]Phase 1 error: {exc}[/red]")
        phase1 = Phase1Result(
            intent="general_query",
            tier="LOW",
            safety_band="GREEN",
            entities={},
            emotion="neutral",
            confidence=0.3,
            gaps=[],
            classifier_degraded=True,
        )
        degraded = True
    _ = int((time.time() - classify_start) * 1000)  # classify timing

    if degraded:
        console.print(
            f"  [yellow]Phase 1 (heuristic fallback): confidence={phase1.confidence:.2f}[/yellow]"
        )

    # ---- CRISIS path ----
    if phase1.safety_band == "CRISIS":
        fsm.transition(Event.CRISIS_DETECTED)
        p1_ops = _phase1_system_writes(manager, phase1, turn_number)
        session_ops.extend(p1_ops)

        console.print("\n  [red]CRISIS DETECTED[/red] -- Static response, no LLM")

        _show_concierge_response(CRISIS_RESPONSE)

        result = ReActResult(final_response=CRISIS_RESPONSE)
        fsm.transition(Event.RESPONSE_DELIVERED)
        p3_ops = _phase3_turn_logger(
            manager, fsm, turn_number, user_message, CRISIS_RESPONSE, result
        )
        session_ops.extend(p3_ops)

        _show_fsm_transitions(
            [
                ("LISTENING", "message_received", "ACKING"),
                ("ACKING", "crisis_detected", "DELIVERING"),
                ("DELIVERING", "response_delivered", "LISTENING"),
            ],
            phase1,
        )

        elapsed_ms = int((time.time() - turn_start) * 1000)
        _show_system_activity(turn_number, elapsed_ms, session_ops, [], 0)
        _show_session_state_panel(manager)
        _clear_special_flags(classifier, hint)
        return {"elapsed_ms": elapsed_ms, "llm_calls": 0, "tool_calls": 0}

    # ---- CLARIFICATION path ----
    if phase1.gaps:
        fsm.transition(Event.GAPS_DETECTED)
        phase1, clar_ops = await _run_clarification(
            manager, fsm, classifier, user_message, phase1, hint, llm
        )
        session_ops.extend(clar_ops)

        # Cancel during clarification: hard stop, no LLM call
        if getattr(phase1, "_cancelled", False):
            CANCEL_RESPONSE = (
                "Got it -- I've stopped working on that. " "What would you like to do instead?"
            )
            console.print("\n  [red]CANCEL[/red] -- hard stop, no further LLM calls")
            _show_concierge_response(CANCEL_RESPONSE)
            result = ReActResult(
                final_response=CANCEL_RESPONSE,
                interrupted=True,
                interrupt_source="cancel",
            )
            # FSM: go to DELIVERING -> LISTENING
            if fsm.state in (State.DISPATCHING, State.COMPANIONING, State.PROGRESSING):
                fsm.transition(Event.DISPATCH_COMPLETE)
            elif fsm.state == State.ACKING:
                fsm.transition(Event.PHASE1_COMPLETE)
                fsm.transition(Event.DISPATCH_COMPLETE)
            if fsm.state == State.DELIVERING:
                fsm.transition(Event.RESPONSE_DELIVERED)
            elif fsm.state != State.LISTENING:
                fsm.reset()

            p3_ops = _phase3_turn_logger(
                manager, fsm, turn_number, user_message, CANCEL_RESPONSE, result
            )
            session_ops.extend(p3_ops)

            elapsed_ms = int((time.time() - turn_start) * 1000)
            _show_system_activity(turn_number, elapsed_ms, session_ops, [], 0)
            _show_session_state_panel(manager)
            _clear_special_flags(classifier, hint)
            return {"elapsed_ms": elapsed_ms, "llm_calls": 0, "tool_calls": 0}

        # After clarification, FSM should be in ACKING or DISPATCHING
        if fsm.state == State.ACKING:
            fsm.transition(Event.PHASE1_COMPLETE)
    else:
        # Normal path
        fsm.transition(Event.PHASE1_COMPLETE)

    # Phase 1 system writes (CRITICAL)
    p1_ops = _phase1_system_writes(manager, phase1, turn_number)
    session_ops.extend(p1_ops)

    # ---- CB-OPEN deterministic fallback (F24) ----
    # When all circuit breakers are open, bypass the LLM entirely and
    # return an honest static response.  The model MUST NOT be called
    # because it will hallucinate "I searched and found ..." despite
    # having no tool results.
    if phase1.entities.get("_force_cb_open") == "true":
        CB_OPEN_RESPONSE = (
            "I'm having trouble connecting to our booking and search services "
            "right now. I can still help you plan using what I already know "
            "about your trip. Once services are restored I'll pick up where "
            "we left off. What would you like to work on in the meantime?"
        )
        console.print("\n  [yellow]CB-OPEN[/yellow] -- Deterministic fallback (no LLM)")
        _show_concierge_response(CB_OPEN_RESPONSE)

        result = ReActResult(final_response=CB_OPEN_RESPONSE)

        # FSM: DISPATCHING -> DELIVERING -> LISTENING
        if fsm.state in (State.DISPATCHING, State.COMPANIONING, State.PROGRESSING):
            fsm.transition(Event.DISPATCH_COMPLETE)
        if fsm.state == State.DELIVERING:
            fsm.transition(Event.RESPONSE_DELIVERED)
        elif fsm.state != State.LISTENING:
            fsm.reset()

        p3_ops = _phase3_turn_logger(
            manager, fsm, turn_number, user_message, CB_OPEN_RESPONSE, result
        )
        session_ops.extend(p3_ops)

        elapsed_ms = int((time.time() - turn_start) * 1000)
        _show_system_activity(turn_number, elapsed_ms, session_ops, [], 0)
        _show_session_state_panel(manager)
        _clear_special_flags(classifier, hint)
        return {"elapsed_ms": elapsed_ms, "llm_calls": 0, "tool_calls": 0}

    # Phase 2: ReAct loop
    session_overview = read_session_state(manager, section=None)
    tool_declarations = registry.get_llm_declarations(phase1.tier)

    # Build enriched user message with clarification context so the LLM
    # knows what the user already answered during clarification rounds.
    #
    # RC-1 fix: If the user interrupted during clarification, the phase1
    # was reclassified from the interrupt message.  Use the INTERRUPT
    # message as the primary query, not the original user message --
    # otherwise the LLM never sees "vegetarian only" / "pizza instead".
    _interrupt_during_clar = getattr(phase1, "_interrupt_message", None)
    if _interrupt_during_clar:
        # Interrupt replaces the original intent
        llm_user_message = f"{_interrupt_during_clar}\n\n" f"[Original request was: {user_message}]"
    else:
        llm_user_message = user_message
    clar_ctx = getattr(phase1, "_clarification_context", None)
    if clar_ctx:
        answers_text = "; ".join(f"{a}" for _, a in clar_ctx if a != "no additional info")
        if answers_text:
            llm_user_message = f"{llm_user_message}\n\n" f"[User already clarified: {answers_text}]"

    _show_llm_call(
        build_system_prompt(
            fsm_state=fsm.state.value,
            turn_number=turn_number,
            tier=phase1.tier,
            safety_band=phase1.safety_band,
            session_overview=session_overview.get("data"),
            tool_declarations=tool_declarations,
            family_persona=_scenario_persona,
        ),
        2,
        len(tool_declarations),
        phase1.tier,
    )

    live_display = LiveLoopDisplay()
    loop = ReActLoop(fsm, registry, llm, scratchpad, event_handler=live_display)

    # Set up interrupt BEFORE loop.run() so it is caught at the top of
    # iteration 1.  The old asyncio.sleep(0.8) approach was unreliable
    # because the LLM call (8-17s) blocked the event loop and the flag
    # was never checked before the loop completed.
    if hint.interrupt_message and not any("INTERRUPT" in op for op in session_ops):
        console.print(f'\n  [red]INTERRUPT QUEUED[/red]: "{hint.interrupt_message}"')
        loop.signal_interrupt(source="user", replacement_message=hint.interrupt_message)

    llm_start = time.time()
    try:
        with Live(
            live_display,
            console=console,
            refresh_per_second=10,
            transient=True,
        ) as live:
            live_display.attach_live(live)
            result = await loop.run(
                phase1,
                llm_user_message,
                turn_number=turn_number,
                session_overview=session_overview.get("data"),
                family_persona=_scenario_persona,
            )
        # Print a static final snapshot so the result is visible
        # in scrollback after Live clears its transient frames.
        console.print(live_display)
    except Exception as exc:
        console.print(f"  [red]ReAct loop error: {exc}[/red]")
        result = ReActResult(
            error=str(exc),
            final_response="I encountered an issue processing your request.",
        )
    llm_elapsed_ms = int((time.time() - llm_start) * 1000)

    # Show LLM response
    _show_llm_response(
        llm_elapsed_ms,
        [],  # tool calls are shown in system activity
        result.final_response[:100] if result.final_response else None,
    )

    # Show tool executions from scratchpad
    for entry in scratchpad.tool_history:
        tool_execs.append(entry.tool_name)

    # Show FSM transitions
    _show_fsm_transitions(result.fsm_transitions, phase1)

    # Handle interrupt result
    if result.interrupted and hint.interrupt_message:
        console.print(
            f"\n  [yellow]INTERRUPT HANDLED[/yellow] -- "
            f'Re-processing: "{hint.interrupt_message}"'
        )
        session_ops.append(f"interrupt.handled(source={result.interrupt_source})")

        # --- CANCEL hard-stop: if the interrupt is a cancellation,
        # do NOT re-run the LLM. Return a deterministic ack.
        _CANCEL_KEYWORDS = frozenset(
            {
                "cancel",
                "stop",
                "never mind",
                "nevermind",
                "forget it",
                "drop it",
                "skip it",
                "abort",
            }
        )
        _int_lower = hint.interrupt_message.lower()
        if any(kw in _int_lower for kw in _CANCEL_KEYWORDS):
            CANCEL_RESPONSE = (
                "Got it -- I've stopped working on that. " "What would you like to do instead?"
            )
            console.print("\n  [red]CANCEL DETECTED[/red] -- hard stop, no further LLM calls")
            _show_concierge_response(CANCEL_RESPONSE)
            result = ReActResult(
                final_response=CANCEL_RESPONSE,
                interrupted=True,
                interrupt_source="cancel",
            )
            # Skip the entire re-processing block below
        else:
            # --- Normal interrupt re-processing (non-cancel) ---
            # Reclassify interrupt message
            phase1_int = classifier.classify_with_fallback(hint.interrupt_message, "interrupted")

            # Bind the interrupt constraint to beliefs so the LLM sees it
            _bind_interrupt_to_beliefs(manager, hint.interrupt_message, turn_number)

            if phase1_int.gaps:
                fsm.transition(Event.GAPS_DETECTED)
                phase1_int, int_ops = await _run_clarification(
                    manager, fsm, classifier, hint.interrupt_message, phase1_int, hint, llm
                )
                session_ops.extend(int_ops)
                if fsm.state == State.ACKING:
                    fsm.transition(Event.PHASE1_COMPLETE)
            else:
                fsm.transition(Event.PHASE1_COMPLETE)

            _phase1_system_writes(manager, phase1_int, turn_number)

            scratchpad2 = Scratchpad()
            live_display2 = LiveLoopDisplay()
            loop2 = ReActLoop(fsm, registry, llm, scratchpad2, event_handler=live_display2)
            overview2 = read_session_state(manager, section=None)

            _show_llm_call(
                build_system_prompt(
                    fsm_state=fsm.state.value,
                    turn_number=turn_number,
                    tier=phase1_int.tier,
                    safety_band=phase1_int.safety_band,
                    session_overview=overview2.get("data"),
                    tool_declarations=registry.get_llm_declarations(phase1_int.tier),
                    family_persona=_scenario_persona,
                ),
                3,
                len(registry.get_llm_declarations(phase1_int.tier)),
                phase1_int.tier,
            )

            llm_start2 = time.time()
            try:
                with Live(
                    live_display2,
                    console=console,
                    refresh_per_second=10,
                    transient=True,
                ) as live2:
                    live_display2.attach_live(live2)
                    result = await loop2.run(
                        phase1_int,
                        hint.interrupt_message,
                        turn_number=turn_number,
                        session_overview=overview2.get("data"),
                        family_persona=_scenario_persona,
                    )
                console.print(live_display2)
            except Exception as exc:
                console.print(f"  [red]ReAct loop error (post-interrupt): {exc}[/red]")
                result = ReActResult(
                    error=str(exc),
                    final_response="I encountered an issue after the interrupt.",
                )
            llm_elapsed2 = int((time.time() - llm_start2) * 1000)
            _show_llm_response(
                llm_elapsed2, [], result.final_response[:100] if result.final_response else None
            )
            _show_fsm_transitions(result.fsm_transitions, phase1_int)

            for entry in scratchpad2.tool_history:
                tool_execs.append(entry.tool_name)

    # Show response
    response_text = result.final_response or ""
    if not response_text.strip():
        # Empty response fallback -- the LLM returned nothing useful.
        # Provide an honest fallback instead of showing "(no response)".
        response_text = (
            "I'm still working on that -- let me gather more details "
            "and get back to you shortly."
        )
    _show_concierge_response_typewriter(response_text)

    # FSM: DELIVERING -> LISTENING
    if fsm.state == State.DELIVERING:
        fsm.transition(Event.RESPONSE_DELIVERED)
    elif fsm.state != State.LISTENING:
        console.print(f"  [yellow]FSM in {fsm.state.value}, forcing to LISTENING.[/yellow]")
        fsm.reset()

    # Phase 3 turn logger (CRITICAL)
    p3_ops = _phase3_turn_logger(manager, fsm, turn_number, user_message, response_text, result)
    session_ops.extend(p3_ops)

    # System activity panel
    elapsed_ms = int((time.time() - turn_start) * 1000)
    _show_system_activity(
        turn_number,
        elapsed_ms,
        session_ops,
        tool_execs,
        result.tool_calls_made * 200,  # approximate bytes
    )
    _show_session_state_panel(manager)

    # Clear special flags (also clears on early-return paths above)
    _clear_special_flags(classifier, hint)

    return {
        "elapsed_ms": elapsed_ms,
        "llm_calls": llm.total_calls,
        "tool_calls": result.tool_calls_made,
    }


# ---------------------------------------------------------------------------
# Interactive mode: --guided
# ---------------------------------------------------------------------------


async def _run_guided_mode(
    manager: SessionStateManager,
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    registry: Any,
    llm: GeminiClient,
) -> None:
    """Scenario-guided interactive mode.

    Iterates the 20-turn ``TRIP_TIMELINE`` showing hints for each turn.
    The user can type a custom message or press Enter to use the
    suggested message.
    """
    total_turns = len(TRIP_TIMELINE)
    last_act: str | None = None

    console.print(
        "\n[bold cyan]GUIDED MODE[/bold cyan]"
        "\nYou will see suggested messages for each turn."
        "\nType your own message or press Enter to use the suggestion.\n"
    )

    for hint in TRIP_TIMELINE:
        # Show ACT header if entering a new act
        act_info = _get_act(hint.turn_number)
        if act_info:
            label, title = act_info
            if label != last_act:
                act_turns = []
                for al, at, ats in ACTS:
                    if al == label:
                        act_turns = ats
                _show_act_header(label, title, act_turns)
                last_act = label

        # Show suggestion
        console.print(f'\n  [dim italic]Suggested: "{hint.suggested_message}"[/dim italic]')
        raw = console.input(f"  [Turn {hint.turn_number}] You: ").strip()

        if raw:
            message = raw
        else:
            message = hint.suggested_message
            console.print("  [dim](using suggested message)[/dim]")

        await _run_turn(
            hint.turn_number,
            total_turns,
            hint,
            manager,
            fsm,
            classifier,
            registry,
            llm,
            override_message=message,
        )

        _pause()


# ---------------------------------------------------------------------------
# Interactive mode: --user
# ---------------------------------------------------------------------------


async def _run_user_mode(
    manager: SessionStateManager,
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    registry: Any,
    llm: GeminiClient,
) -> None:
    """Free-form interactive chat mode (no scenario).

    Runs an infinite chat loop where the user types messages freely.
    Type 'quit', 'exit', 'bye', or 'q' to end the session.
    """
    console.print(
        "\n[bold cyan]FREE-FORM MODE[/bold cyan]"
        "\nType your message to the concierge. No scenario -- just chat."
        "\nType 'quit' or 'exit' to end.\n"
    )

    turn = 1
    while True:
        raw = console.input(f"\n  [Turn {turn}] You: ").strip()
        if raw.lower() in ("quit", "exit", "bye", "q"):
            console.print("\n[dim]Ending session...[/dim]")
            break
        if not raw:
            continue

        # Create minimal TurnHint for the free-form message
        hint = TurnHint(
            turn_number=turn,
            flow_id=f"U{turn}",
            suggested_message=raw,
            description=f"User free-form turn {turn}",
        )

        await _run_turn(
            turn,
            0,  # total_turns=0 signals open-ended
            hint,
            manager,
            fsm,
            classifier,
            registry,
            llm,
            override_message=raw,
        )

        turn += 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def main(auto: bool = False, mode: str = "scripted") -> None:
    """Run the concierge demo.

    Parameters
    ----------
    auto:
        When True, skips pauses between turns (scripted mode only).
    mode:
        One of ``"scripted"`` (default), ``"auto"``, ``"user"``, ``"guided"``.
    """
    global _auto_mode, _interactive_mode, _scenario_persona  # noqa: PLW0603
    _auto_mode = auto or mode == "auto"
    _interactive_mode = mode in ("user", "guided")
    _scenario_persona = FAMILY_PERSONA if mode != "user" else None

    import os

    # Load .env for GOOGLE_API_KEY if available
    env_file = Path(__file__).resolve().parents[1] / "chat_experience_poc" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip("\"'"))

    _show_banner(mode)

    _pause("\n  >> Press Enter to begin the demo...\n")

    # Initialize -- wipe previous session DB so each run starts clean
    session_id = f"trip-demo-{uuid.uuid4().hex[:8]}"
    db_path = Path.home() / ".familyos" / "poc" / "concierge_fsm.db"
    if db_path.exists():
        try:
            db_path.unlink()
            console.print("[dim][SYSTEM] Previous session DB cleared[/dim]")
        except OSError as exc:
            console.print(f"[yellow][SYSTEM] Could not remove old DB: {exc}[/yellow]")

    manager = SessionStateFactory.create_standalone(session_id=session_id, db_path=db_path)
    manager.start()

    fsm = FSMController()
    classifier = MockPhase1Classifier()
    cognitive = CognitiveToolSet(manager)
    registry = build_default_registry(cognitive, manager)
    llm = GeminiClient()

    # Persona pre-load: only for scenario modes (scripted/guided/auto).
    # In --user mode, the session starts blank -- no pre-assumed family.
    if mode != "user":
        reset_memory_corpus()  # Ensure scenario memory corpus is active
        try:
            persona_sec = manager.get_section("persona")
            persona_sec.set_warmth(0.8)
            persona_sec.set_formality(0.3)
            persona_sec.set_verbosity(0.5)
        except Exception:
            pass  # POC: persona pre-load best-effort

        # Pre-load family persona data into beliefs_active so the LLM knows
        # about family members, allergies, ages, and preferences from Turn 1.
        for member in FAMILY_PERSONA.get("members", []):
            name = member.get("name", "Unknown")
            role = member.get("role", "member")
            try:
                manager.mutate(
                    "beliefs_active",
                    "add_fact",
                    {
                        "subject": name,
                        "predicate": "is_family",
                        "obj": role,
                        "confidence": 1.0,
                        "source": "persona_preload",
                    },
                )
            except Exception:
                pass
            # Allergies
            for allergy in member.get("allergies", []):
                try:
                    manager.mutate(
                        "beliefs_active",
                        "add_fact",
                        {
                            "subject": name,
                            "predicate": "allergic_to",
                            "obj": allergy,
                            "confidence": 1.0,
                            "source": "persona_preload",
                        },
                    )
                except Exception:
                    pass
            # Age (for children)
            age = member.get("age")
            if age:
                try:
                    manager.mutate(
                        "beliefs_active",
                        "add_fact",
                        {
                            "subject": name,
                            "predicate": "age",
                            "obj": str(age),
                            "confidence": 1.0,
                            "source": "persona_preload",
                        },
                    )
                except Exception:
                    pass
            # Preferences
            for pref in member.get("preferences", []):
                try:
                    manager.mutate(
                        "beliefs_active",
                        "add_fact",
                        {
                            "subject": name,
                            "predicate": "prefers",
                            "obj": pref,
                            "confidence": 0.9,
                            "source": "persona_preload",
                        },
                    )
                except Exception:
                    pass
        # Home location
        try:
            manager.mutate(
                "beliefs_active",
                "add_fact",
                {
                    "subject": "family",
                    "predicate": "home_location",
                    "obj": FAMILY_PERSONA.get("home_location", "unknown"),
                    "confidence": 1.0,
                    "source": "persona_preload",
                },
            )
        except Exception:
            pass

    console.print(f"[dim][SYSTEM] Session started: {session_id}[/dim]")
    console.print(f"[dim][SYSTEM] DB: {db_path}[/dim]")
    console.print("[dim][SYSTEM] ConciergeFSM initialized as orchestrator[/dim]")
    console.print(f"[dim][SYSTEM] {len(registry)} tools registered[/dim]")
    if mode != "user":
        console.print(
            f"[dim][SYSTEM] Persona loaded: {FAMILY_PERSONA['family_name']} "
            f"({len(FAMILY_PERSONA['members'])} members)[/dim]"
        )
    else:
        clear_memory_corpus()  # No pre-loaded family memories in free-form mode
        console.print("[dim][SYSTEM] No persona pre-loaded (free-form mode)[/dim]")
        console.print("[dim][SYSTEM] Long-term memory cleared (fresh start)[/dim]")

    console.print(f"[dim][SYSTEM] Mode: {mode}[/dim]")

    total_start = time.time()
    total_llm_calls_baseline = llm.total_calls

    try:
        if mode == "user":
            await _run_user_mode(manager, fsm, classifier, registry, llm)
        elif mode == "guided":
            await _run_guided_mode(manager, fsm, classifier, registry, llm)
        else:
            # Scripted or auto mode -- run the 20-turn timeline
            total_turns = len(TRIP_TIMELINE)
            last_act: str | None = None

            for hint in TRIP_TIMELINE:
                # Show ACT header if entering a new act
                act_info = _get_act(hint.turn_number)
                if act_info:
                    label, title = act_info
                    if label != last_act:
                        act_turns = []
                        for al, at, ats in ACTS:
                            if al == label:
                                act_turns = ats
                        _show_act_header(label, title, act_turns)
                        last_act = label

                _pause()

                await _run_turn(
                    hint.turn_number,
                    total_turns,
                    hint,
                    manager,
                    fsm,
                    classifier,
                    registry,
                    llm,
                )

    except KeyboardInterrupt:
        console.print("\n[yellow]Demo interrupted by user.[/yellow]")
    finally:
        total_ms = int((time.time() - total_start) * 1000)
        total_turns_ran = len(TRIP_TIMELINE) if mode in ("scripted", "auto") else 0
        _show_session_summary(
            fsm,
            manager,
            total_turns_ran,
            total_ms,
            llm.total_calls - total_llm_calls_baseline,
            llm.total_tokens_in,
            llm.total_tokens_out,
        )

        try:
            manager.stop()
            console.print("[green]Session closed.[/green]")
        except Exception as exc:
            console.print(f"[red]Cleanup error: {exc}[/red]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Concierge FSM Demo")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--auto",
        action="store_true",
        help="Scripted mode without pausing between turns",
    )
    group.add_argument(
        "--user",
        action="store_true",
        help="Free-form interactive chat (no scenario)",
    )
    group.add_argument(
        "--guided",
        action="store_true",
        help="Scenario-guided mode (shows hints, you type)",
    )
    args = parser.parse_args()

    if args.user:
        mode = "user"
    elif args.guided:
        mode = "guided"
    elif args.auto:
        mode = "auto"
    else:
        mode = "scripted"

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main(auto=args.auto, mode=mode))
