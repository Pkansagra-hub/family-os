"""Rich TUI Demo Runner -- Epic 4.1 (DEMO-001, DEMO-002).

Interactive entry point for the Concierge FSM PoC.  Drives a 20-turn Lake
Tahoe family trip conversation through the full FSM pipeline:

    Phase 1: classify (MockPhase1Classifier)
    Phase 2: ReAct loop (GeminiClient + ToolRegistry + Scratchpad)
    Phase 3: Turn logger (history_active + meta writes)

Uses ``rich`` for styled terminal panels showing FSM state, classification
results, tool calls, and session state diffs.

Usage:
    python -m poc.concierge_fsm_poc.demo
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from k1.sessionstate import SessionStateFactory, SessionStateManager
from poc.concierge_fsm_poc.fsm.controller import Event, FSMController, InvalidTransitionError, State
from poc.concierge_fsm_poc.fsm.phase1_mock import MockPhase1Classifier, Phase1Result
from poc.concierge_fsm_poc.llm.client import GeminiClient
from poc.concierge_fsm_poc.react.loop import ReActLoop, ReActResult
from poc.concierge_fsm_poc.react.scratchpad import Scratchpad
from poc.concierge_fsm_poc.scenarios.trip_timeline import (
    CRISIS_RESPONSE,
    FAMILY_PERSONA,
    TRIP_TIMELINE,
    TurnHint,
    get_hint,
)
from poc.concierge_fsm_poc.tools.cognitive import CognitiveToolSet
from poc.concierge_fsm_poc.tools.read_mock import read_session_state
from poc.concierge_fsm_poc.tools.registry import build_default_registry
from poc.concierge_fsm_poc.tools.signal import reset_ack_log

logger = logging.getLogger("concierge_fsm.demo")
console = Console()

MAX_CLARIFICATION_ROUNDS = 3


# ---------------------------------------------------------------------------
# DEMO-002: Session initialization
# ---------------------------------------------------------------------------


async def initialize() -> (
    tuple[SessionStateManager, FSMController, MockPhase1Classifier, Any, GeminiClient]
):
    """Wire SessionStateManager, FSM, classifier, tool registry, and LLM.

    Returns (manager, fsm, classifier, registry, llm).
    """
    session_id = f"trip-demo-{uuid.uuid4().hex[:8]}"
    db_path = Path.home() / ".familyos" / "poc" / "concierge_fsm.db"

    manager = SessionStateFactory.create_standalone(session_id=session_id, db_path=db_path)
    manager.start()

    # FSM
    fsm = FSMController()

    # Phase 1 classifier
    classifier = MockPhase1Classifier()

    # Tools
    cognitive = CognitiveToolSet(manager)
    registry = build_default_registry(cognitive, manager)

    # LLM
    llm = GeminiClient()

    # Persona pre-load (persona section has no generic update; load traits directly)
    try:
        persona_sec = manager.get_section("persona")
        persona_sec.set_warmth(0.8)
        persona_sec.set_formality(0.3)
        persona_sec.set_verbosity(0.5)
    except Exception:
        pass  # POC: persona pre-load best-effort

    console.print(
        Panel(
            f"[bold]Session:[/bold] {session_id}\n"
            f"[bold]DB:[/bold] {db_path}\n"
            f"[bold]Tools:[/bold] {len(registry)} registered\n"
            f"[bold]Persona:[/bold] {FAMILY_PERSONA['family_name']} "
            f"({len(FAMILY_PERSONA['members'])} members)",
            title="[bold green]Concierge FSM PoC -- Lake Tahoe Trip[/bold green]",
            border_style="green",
        )
    )

    return manager, fsm, classifier, registry, llm


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _show_fsm_header(fsm: FSMController, turn_number: int) -> None:
    """Render the FSM state header bar."""
    state_colours = {
        State.LISTENING: "green",
        State.ACKING: "yellow",
        State.CLARIFYING: "cyan",
        State.DISPATCHING: "blue",
        State.COMPANIONING: "magenta",
        State.PROGRESSING: "magenta",
        State.DELIVERING: "bold green",
        State.INTERRUPT_HANDLING: "red",
    }
    colour = state_colours.get(fsm.state, "white")
    console.rule(f"[{colour}]FSM: {fsm.state.value}[/{colour}]  |  Turn {turn_number}")


def _show_hint(hint: TurnHint | None, turn_number: int) -> None:
    """Display the story hint for the current turn."""
    if hint is None:
        console.print(f"[dim]Turn {turn_number}: No story hint (free play)[/dim]")
        return
    lines = [
        f"[bold]Flow {hint.flow_id}[/bold] -- {hint.description}",
        f"[dim]Suggested:[/dim] {hint.suggested_message}",
    ]
    if hint.interrupt_message:
        lines.append(f"[dim]Interrupt:[/dim] {hint.interrupt_message}")
    if hint.clarification_answers:
        lines.append(f"[dim]Clarifications:[/dim] {', '.join(hint.clarification_answers)}")
    if hint.special_flags:
        lines.append(f"[dim]Flags:[/dim] {hint.special_flags}")
    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]Story Hint -- Turn {turn_number}[/bold cyan]",
            border_style="cyan",
        )
    )


def _show_classification(phase1: Phase1Result, degraded: bool = False) -> None:
    """Display Phase 1 classification results."""
    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Key", style="bold")
    tbl.add_column("Value")
    tbl.add_row("Intent", phase1.intent)
    tbl.add_row("Tier", phase1.tier)
    tbl.add_row("Safety", phase1.safety_band)
    tbl.add_row("Emotion", phase1.emotion)
    tbl.add_row("Confidence", f"{phase1.confidence:.2f}")
    if phase1.entities:
        tbl.add_row("Entities", str(phase1.entities))
    if phase1.gaps:
        tbl.add_row("Gaps", ", ".join(phase1.gaps))
    label = (
        "[bold yellow]Phase 1 (heuristic fallback)[/bold yellow]"
        if degraded
        else "[bold yellow]Phase 1 Classification[/bold yellow]"
    )
    console.print(Panel(tbl, title=label, border_style="yellow"))


def _show_react_result(result: ReActResult) -> None:
    """Display the ReAct loop result with FSM transitions."""
    # FSM transitions table
    if result.fsm_transitions:
        tbl = Table(title="FSM Transitions (Phase 2)", show_lines=True)
        tbl.add_column("From", style="cyan")
        tbl.add_column("Event", style="yellow")
        tbl.add_column("To", style="green")
        for from_s, evt, to_s in result.fsm_transitions:
            tbl.add_row(from_s, evt, to_s)
        console.print(tbl)

    # Metrics
    metrics = (
        f"Iterations: {result.iterations}  |  "
        f"Tool calls: {result.tool_calls_made}  |  "
        f"Findings: {result.findings_count}"
    )
    if result.budget_exhausted:
        metrics += "  |  [bold red]BUDGET EXHAUSTED[/bold red]"
    if result.interrupted:
        metrics += f"  |  [bold red]INTERRUPTED ({result.interrupt_source})[/bold red]"
    console.print(f"[dim]{metrics}[/dim]")

    # Final response
    if result.final_response:
        console.print(
            Panel(
                result.final_response,
                title="[bold green]Response[/bold green]",
                border_style="green",
            )
        )

    # Error
    if result.error:
        console.print(
            Panel(
                result.error,
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )


def _show_state_diff(manager: SessionStateManager) -> None:
    """Display a condensed SessionState overview."""
    try:
        overview = read_session_state(manager, section=None)
        data = overview.get("data", {})
        tbl = Table(title="SessionState Overview", show_lines=True)
        tbl.add_column("Section", style="cyan")
        tbl.add_column("Details", style="white")
        for sect_name, sect_data in data.items():
            if isinstance(sect_data, dict):
                details = ", ".join(f"{k}={v}" for k, v in sect_data.items() if k != "error")
            else:
                details = str(sect_data)
            tbl.add_row(sect_name, details or "(empty)")
        console.print(tbl)
    except Exception as exc:
        console.print(f"[red]SessionState read error: {exc}[/red]")


def _show_fsm_history(fsm: FSMController) -> None:
    """Display full FSM transition history."""
    history = fsm.history
    if not history:
        console.print("[dim]No FSM transitions yet.[/dim]")
        return
    tbl = Table(title="FSM Transition History", show_lines=True)
    tbl.add_column("#", style="dim")
    tbl.add_column("From", style="cyan")
    tbl.add_column("Event", style="yellow")
    tbl.add_column("To", style="green")
    for idx, (from_s, evt, to_s) in enumerate(history, 1):
        tbl.add_row(str(idx), from_s.value, evt.value, to_s.value)
    console.print(tbl)


# ---------------------------------------------------------------------------
# Phase 1 system writes
# ---------------------------------------------------------------------------


def _phase1_system_writes(
    manager: SessionStateManager,
    phase1: Phase1Result,
    turn_number: int,
) -> None:
    """Write Phase 1 outputs into SessionState BEFORE the ReAct loop."""
    # Control section uses set_flow_phase / set_primary_domain -- no generic update.
    try:
        sec = manager.get_section("control")
        sec.set_flow_phase(sec.FlowPhase.TURN_ACTIVE if hasattr(sec, "FlowPhase") else 1)
    except Exception:
        pass
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


# ---------------------------------------------------------------------------
# Phase 3 turn logger
# ---------------------------------------------------------------------------


def _phase3_turn_logger(
    manager: SessionStateManager,
    fsm: FSMController,
    turn_number: int,
    user_message: str,
    final_response: str,
    result: ReActResult,
) -> None:
    """Log the completed turn to SessionState AFTER response delivered."""
    manager.mutate(
        "history_active",
        "append",
        {
            "user_message": user_message,
            "assistant_response": final_response,
        },
    )
    # Meta section has no generic update(); touch is enough for the POC.
    try:
        sec = manager.get_section("meta")
        if hasattr(sec, "touch"):
            sec.touch()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Clarification loop
# ---------------------------------------------------------------------------


async def _clarification_loop(
    manager: SessionStateManager,
    fsm: FSMController,
    classifier: MockPhase1Classifier,
    original_message: str,
    phase1: Phase1Result,
    hint: TurnHint | None,
    turn_number: int,
) -> Phase1Result:
    """Run up to MAX_CLARIFICATION_ROUNDS of clarification.

    Returns the final Phase1Result (either gaps resolved or force-proceeded).
    """
    current_phase1 = phase1
    scripted_idx = 0

    for round_num in range(1, MAX_CLARIFICATION_ROUNDS + 1):
        # Display clarification question
        gaps_text = ", ".join(current_phase1.gaps)
        console.print(
            Panel(
                f"I need a bit more information: {gaps_text}",
                title=f"[bold cyan]Clarification Round {round_num}/{MAX_CLARIFICATION_ROUNDS}[/bold cyan]",
                border_style="cyan",
            )
        )

        # Get clarification answer (scripted or user input)
        if hint and scripted_idx < len(hint.clarification_answers):
            answer = hint.clarification_answers[scripted_idx]
            console.print(f"[dim](scripted answer: {answer})[/dim]")
            scripted_idx += 1
        else:
            answer = console.input("[bold]Clarification> [/bold]")

        if not answer.strip():
            answer = "no additional info"

        # Check for interrupt during clarification
        if hint and hint.interrupt_message and answer.lower() == hint.interrupt_message.lower():
            # Interrupt at clarification
            fsm.transition(Event.INTERRUPT_DETECTED)
            fsm.transition(Event.INTERRUPT_HANDLED)
            console.print("[bold red]Interrupt during clarification[/bold red]")
            # Re-classify with the interrupt message
            enriched = f"{original_message} | clarification: {answer}"
            current_phase1 = classifier.classify_with_fallback(
                hint.interrupt_message, f"original:{enriched}"
            )
            return current_phase1

        # FSM: CLARIFYING -> ACKING via CLARIFICATION_RECEIVED
        fsm.transition(Event.CLARIFICATION_RECEIVED)

        # Re-classify with enriched context
        enriched = f"{original_message} | clarification: {answer}"
        current_phase1 = classifier.classify_with_fallback(enriched, f"round:{round_num}")

        if not current_phase1.gaps:
            # Gaps resolved
            console.print("[green]Gaps resolved.[/green]")
            return current_phase1

        if round_num < MAX_CLARIFICATION_ROUNDS:
            # More rounds -- FSM stays in ACKING, fire GAPS_DETECTED -> CLARIFYING
            fsm.transition(Event.GAPS_DETECTED)

    # Max rounds exhausted -- force-proceed
    console.print("[yellow]Max clarification rounds reached. Force-proceeding.[/yellow]")
    fsm.transition(Event.MAX_ROUNDS_REACHED)
    return current_phase1


# ---------------------------------------------------------------------------
# DEMO-001: Main loop
# ---------------------------------------------------------------------------


async def main() -> None:
    """Interactive Rich TUI main loop."""
    manager, fsm, classifier, registry, llm = await initialize()

    turn_number = 0
    total_turns = len(TRIP_TIMELINE)

    console.print(
        f"\n[bold]Type a message to start. "
        f"Commands: [cyan]quit[/cyan] [cyan]exit[/cyan] "
        f"[cyan]snapshot[/cyan] [cyan]history[/cyan] "
        f"[cyan]auto[/cyan] (use suggested message)[/bold]\n"
        f"[dim]{total_turns} story turns available.[/dim]\n"
    )

    try:
        while True:
            turn_number += 1
            hint = get_hint(turn_number)

            # Display header + hint
            _show_fsm_header(fsm, turn_number)
            _show_hint(hint, turn_number)

            # Get user input
            user_input = console.input("\n[bold]You> [/bold]").strip()

            # --- Commands ------------------------------------------------
            if user_input.lower() in ("quit", "exit"):
                break

            if user_input.lower() == "snapshot":
                _show_state_diff(manager)
                turn_number -= 1  # don't consume a turn
                continue

            if user_input.lower() == "history":
                _show_fsm_history(fsm)
                turn_number -= 1
                continue

            if user_input.lower() == "auto" and hint:
                user_input = hint.suggested_message
                console.print(f"[dim](auto: {user_input})[/dim]")

            if not user_input:
                console.print("[dim]Empty input, try again.[/dim]")
                turn_number -= 1
                continue

            # --- Apply special flags from hint ---------------------------
            if hint and hint.special_flags:
                for flag, value in hint.special_flags.items():
                    if hasattr(classifier, flag):
                        setattr(classifier, flag, value)
                        console.print(f"[dim](flag: {flag}={value})[/dim]")

            # --- Reset per-turn state ------------------------------------
            reset_ack_log()
            scratchpad = Scratchpad()

            # --- FSM: LISTENING -> ACKING --------------------------------
            try:
                fsm.transition(Event.MESSAGE_RECEIVED)
            except InvalidTransitionError:
                # If FSM is not in LISTENING (e.g. stuck), reset
                console.print(
                    f"[yellow]FSM not in LISTENING ({fsm.state.value}), resetting.[/yellow]"
                )
                fsm.reset()
                fsm.transition(Event.MESSAGE_RECEIVED)

            # --- Phase 1: Classify ---------------------------------------
            degraded = False
            try:
                phase1 = classifier.classify_with_fallback(user_input, f"turn:{turn_number}")
                degraded = phase1.classifier_degraded
            except Exception as exc:
                console.print(f"[red]Phase 1 error: {exc}[/red]")
                # Emergency fallback
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

            _show_classification(phase1, degraded=degraded)

            # --- CRISIS path ---------------------------------------------
            if phase1.safety_band == "CRISIS":
                fsm.transition(Event.CRISIS_DETECTED)
                console.print(
                    Panel(
                        CRISIS_RESPONSE,
                        title="[bold red]CRISIS RESPONSE[/bold red]",
                        border_style="red",
                    )
                )
                _phase1_system_writes(manager, phase1, turn_number)

                # Phase 3 logger with static response
                result = ReActResult(final_response=CRISIS_RESPONSE)
                fsm.transition(Event.RESPONSE_DELIVERED)
                _phase3_turn_logger(manager, fsm, turn_number, user_input, CRISIS_RESPONSE, result)
                _show_state_diff(manager)
                console.print(
                    f"[dim]Flow {hint.flow_id if hint else '?'} completed (CRISIS bypass)[/dim]"
                )
                continue

            # --- CLARIFICATION path --------------------------------------
            if phase1.gaps:
                fsm.transition(Event.GAPS_DETECTED)
                phase1 = await _clarification_loop(
                    manager, fsm, classifier, user_input, phase1, hint, turn_number
                )
                _show_classification(phase1, degraded=phase1.classifier_degraded)

                # After clarification, FSM should be in ACKING or DISPATCHING
                if fsm.state == State.ACKING:
                    fsm.transition(Event.PHASE1_COMPLETE)
            else:
                # --- Normal path: PHASE1_COMPLETE -> DISPATCHING ---------
                fsm.transition(Event.PHASE1_COMPLETE)

            # --- Phase 1 system writes (CRITICAL) ------------------------
            _phase1_system_writes(manager, phase1, turn_number)

            # --- Phase 2: ReAct loop -------------------------------------
            session_overview = read_session_state(manager, section=None)
            loop = ReActLoop(fsm, registry, llm, scratchpad)

            # Set up interrupt if hint calls for one
            if hint and hint.interrupt_message:
                # Schedule interrupt after a brief delay
                async def _fire_interrupt(react_loop: ReActLoop, msg: str) -> None:
                    await asyncio.sleep(1.0)
                    react_loop.signal_interrupt(source="user", replacement_message=msg)

                asyncio.create_task(_fire_interrupt(loop, hint.interrupt_message))

            try:
                result = await loop.run(
                    phase1,
                    user_input,
                    turn_number=turn_number,
                    session_overview=session_overview.get("data"),
                )
            except Exception as exc:
                console.print(f"[red]ReAct loop error: {exc}[/red]")
                result = ReActResult(
                    error=str(exc),
                    final_response="I encountered an issue processing your request.",
                )

            _show_react_result(result)

            # --- Handle interrupt result ---------------------------------
            if result.interrupted and hint and hint.interrupt_message:
                console.print(
                    f"[bold yellow]Interrupt handled. "
                    f"Re-processing with: {hint.interrupt_message}[/bold yellow]"
                )
                # The interrupt already fired INTERRUPT_DETECTED -> INTERRUPT_HANDLING
                # -> INTERRUPT_HANDLED -> ACKING inside the loop.
                # Now re-classify the interrupt message and re-run.
                phase1_int = classifier.classify_with_fallback(
                    hint.interrupt_message, "interrupted"
                )
                _show_classification(phase1_int)

                if phase1_int.gaps:
                    fsm.transition(Event.GAPS_DETECTED)
                    phase1_int = await _clarification_loop(
                        manager,
                        fsm,
                        classifier,
                        hint.interrupt_message,
                        phase1_int,
                        hint,
                        turn_number,
                    )
                    if fsm.state == State.ACKING:
                        fsm.transition(Event.PHASE1_COMPLETE)
                else:
                    fsm.transition(Event.PHASE1_COMPLETE)

                _phase1_system_writes(manager, phase1_int, turn_number)

                scratchpad2 = Scratchpad()
                loop2 = ReActLoop(fsm, registry, llm, scratchpad2)
                overview2 = read_session_state(manager, section=None)

                try:
                    result = await loop2.run(
                        phase1_int,
                        hint.interrupt_message,
                        turn_number=turn_number,
                        session_overview=overview2.get("data"),
                    )
                except Exception as exc:
                    console.print(f"[red]ReAct loop error (post-interrupt): {exc}[/red]")
                    result = ReActResult(
                        error=str(exc),
                        final_response="I encountered an issue after the interrupt.",
                    )

                _show_react_result(result)

            # --- FSM: DELIVERING -> LISTENING ----------------------------
            if fsm.state == State.DELIVERING:
                fsm.transition(Event.RESPONSE_DELIVERED)
            elif fsm.state != State.LISTENING:
                console.print(
                    f"[yellow]FSM in unexpected state {fsm.state.value}, "
                    f"forcing to LISTENING.[/yellow]"
                )
                fsm.reset()

            # --- Phase 3 turn logger (CRITICAL) --------------------------
            _phase3_turn_logger(
                manager, fsm, turn_number, user_input, result.final_response, result
            )

            # --- Post-turn display ---------------------------------------
            _show_state_diff(manager)
            console.print(f"[dim]Flow {hint.flow_id if hint else '?'} completed[/dim]")

            # Clear special flags after turn
            if hint and hint.special_flags:
                for flag in hint.special_flags:
                    if hasattr(classifier, flag):
                        # Reset to default
                        if flag == "raise_on_next":
                            classifier.raise_on_next = False
                        elif flag == "force_cb_open":
                            classifier.force_cb_open = False
                        elif flag == "watchdog_timeout_ms":
                            classifier.watchdog_timeout_ms = 0

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
    finally:
        # --- Session summary -----------------------------------------
        console.print()
        console.rule("[bold]Session Summary[/bold]")
        console.print(f"[bold]Turns completed:[/bold] {turn_number}")
        console.print(f"[bold]FSM transitions:[/bold] {len(fsm.history)}")

        _show_fsm_history(fsm)
        _show_state_diff(manager)

        # Coverage report: which flows were exercised
        exercised = set()
        for t in range(1, turn_number + 1):
            h = get_hint(t)
            if h:
                exercised.add(h.flow_id)
        all_flows = {h.flow_id for h in TRIP_TIMELINE}
        missing = all_flows - exercised
        console.print(f"\n[bold]Flow coverage:[/bold] {len(exercised)}/{len(all_flows)}")
        if missing:
            console.print(f"[dim]Not exercised: {', '.join(sorted(missing))}[/dim]")

        # Cleanup
        try:
            manager.stop()
            console.print("[green]Session closed.[/green]")
        except Exception as exc:
            console.print(f"[red]Cleanup error: {exc}[/red]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    asyncio.run(main())
