"""
poc.k1_poc.demo.interactive -- Interactive turn loop with device identity.

Reads user input from stdin, resolves device-based identity, publishes
USER_UTTERANCE envelopes onto the K1 bus, and waits for responses on
the output channel.  Supports special commands and auto-play mode.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from poc.k1_poc.bus.builders import build_user_input
from poc.k1_poc.demo.display import (
    print_act_header,
    print_demo_complete,
    print_demo_header,
    print_system_message,
    print_turn_indicator,
    print_user_message,
)
from poc.k1_poc.demo.smith_family import (
    DEVICE_REGISTRY,
    MEMBER_TO_DEFAULT_DEVICE,
    STORYLINE_TURNS,
    resolve_member,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESPONSE_TIMEOUT_S = 180.0
AUTO_PLAY_DELAY_S = 3.0


# ---------------------------------------------------------------------------
# Act helpers
# ---------------------------------------------------------------------------


def _act_for_turn(turn: int) -> str:
    if turn <= 3:
        return "ACT 1: Before Dawn"
    if turn <= 10:
        return "ACT 2: Morning Machine"
    if turn <= 16:
        return "ACT 3: Midday Pressure"
    return "ACT 4: Family Handoff"


def _act_turn_range(turn: int) -> str:
    if turn <= 3:
        return "Turns 1-3"
    if turn <= 10:
        return "Turns 4-10"
    if turn <= 16:
        return "Turns 11-16"
    return "Turns 17-18"


# ---------------------------------------------------------------------------
# InteractiveDemoLoop
# ---------------------------------------------------------------------------


class InteractiveDemoLoop:
    """
    Async interactive loop for the K1 demo.

    Features:
        - Device-based identity: prefix input with [alex], [jordan], etc.
        - Turn counter incremented per input
        - IoT stubs fire at scripted turns
        - Special commands: /quit, /status, /switch, /turn, /replay,
          /timeline, /help
        - Auto-play mode: plays storyline turns with configurable delay
    """

    def __init__(self, coordinator: Any) -> None:
        from poc.k1_poc.demo.coordinator import K1DemoCoordinator

        self._coord: K1DemoCoordinator = coordinator
        self._turn: int = 0
        self._current_device: str = "alex_phone"
        self._current_member: str = "Alex"
        self._running: bool = False

    @property
    def turn(self) -> int:
        return self._turn

    @property
    def current_member(self) -> str:
        return self._current_member

    # -----------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------

    async def run(
        self,
        *,
        auto_play: bool = False,
        story_demo: bool = False,
        walkthrough: bool = False,
        fast: bool = False,
    ) -> None:
        """Run the interactive loop until /quit or Ctrl+C."""
        self._running = True

        if story_demo:
            await self._run_story_demo(walkthrough=walkthrough, fast=fast)
            return

        if auto_play:
            await self._run_auto_play(fast=fast)
            return

        self._print_welcome()

        while self._running:
            try:
                raw = await self._async_input(f"[{self._current_member}@turn{self._turn}] > ")
            except (EOFError, KeyboardInterrupt):
                self._running = False
                break

            raw = raw.strip()
            if not raw:
                continue

            # Handle special commands
            if raw.startswith("/"):
                should_continue = await self._handle_command(raw)
                if not should_continue:
                    break
                continue

            # Parse device prefix  [alex] hello -> device=alex_phone, text=hello
            device, text = self._parse_device_prefix(raw)
            if device:
                self._switch_device(device)

            if not text:
                continue

            # Display the user message with member name
            print_user_message(text, self._current_member)

            # Flush any buffered weave results BEFORE processing the
            # new turn.  These arrived while the user was typing and
            # were held back to avoid corrupting their input.  Render
            # them now so the user sees the updates naturally before
            # the next Concierge response.
            output = self._coord.get_output_channel()
            pending = output.flush_pending_weaves()
            if pending:
                from poc.k1_poc.demo.display import print_concierge_message

                for weave_text in pending:
                    print_concierge_message(f"[update while you were typing]\n{weave_text}")

            await self._process_turn(text)

    async def stop(self) -> None:
        self._running = False

    # -----------------------------------------------------------------
    # Turn processing
    # -----------------------------------------------------------------

    async def _process_turn(self, text: str) -> None:
        """Publish a user utterance and wait for response."""
        self._turn += 1

        # Reset dispatchers at turn START (fresh budget + state).
        # Never reset at turn END -- Front/Back ReAct loops may still
        # be running asynchronously after wait_for_response returns.
        try:
            self._coord.front_dispatcher.reset()
            self._coord.back_dispatcher.reset()
        except Exception:
            pass

        logger.info(
            "TURN: #%d starting -- member=%s device=%s text=%s",
            self._turn,
            self._current_member,
            self._current_device,
            text[:80],
        )

        # Check for IoT events BEFORE this turn
        iot = self._coord.get_iot_stubs()
        if iot.has_event(self._turn):
            logger.info("TURN: IoT event at turn %d", self._turn)
            print_system_message(f"IoT event at turn {self._turn}", "info")
            iot.check(self._turn)
            # Give the bus a moment to process the proactive event
            await asyncio.sleep(0.3)

        output = self._coord.get_output_channel()

        # Update output channel identity and start per-turn tracking
        output.set_member(self._current_member)
        output.start_turn(self._turn)

        # Build and publish USER_UTTERANCE
        payload: dict = {
            "text": text,
            "member": self._current_member,
            "device": self._current_device,
            "turn": self._turn,
        }

        envelope = build_user_input(payload=payload)
        logger.info(
            "TURN: publishing user.input envelope (topic=%s, parent_id=%d)",
            envelope.topic,
            envelope.parent_id,
        )
        bus = self._coord.get_bus()
        bus.publish(envelope)
        logger.info(
            "TURN: user.input published, waiting for response (timeout=%ds)", RESPONSE_TIMEOUT_S
        )

        # Wait for front response -- the initial ack + STANDARD response.
        # After this returns, _process_turn returns to the prompt.
        # Back tasks run asynchronously in the coordinator's consumer loop.
        # Their results (PRESENT/HITL/WEAVE responses) are rendered
        # directly by the output_channel bus handlers as they arrive
        # (V2 Section 4: COMPANIONING keeps the user-facing channel
        # responsive; V2 Section 8.10: Weave Protocol).
        got_response = await output.wait_for_response(timeout=RESPONSE_TIMEOUT_S)
        logger.info("TURN: wait_for_response returned: %s", got_response)
        if self._coord.fsm:
            logger.info(
                "TURN: FSM state after front response: %s (back tasks run in background)",
                self._coord.fsm.state.name,
            )

    # -----------------------------------------------------------------
    # Auto-play mode
    # -----------------------------------------------------------------

    async def _run_auto_play(self, *, fast: bool = False) -> None:
        """Play storyline turns automatically."""
        delay_s = 0.8 if fast else AUTO_PLAY_DELAY_S
        total = max(e["turn"] for e in STORYLINE_TURNS)

        print_demo_header(
            "ONE ORDINARY DAY",
            "A Smith Family Morning",
            f"A {total}-Turn FamilyOS Demo",
        )
        print_system_message(f"Playing {len(STORYLINE_TURNS)} storyline turns")
        print_system_message(f"Delay between turns: {delay_s}s")
        print_system_message("Press Ctrl+C to stop")

        for entry in STORYLINE_TURNS:
            if not self._running:
                break

            turn_num = entry["turn"]
            device = entry["device"]
            text = entry["text"]

            # Switch device
            self._switch_device(device)

            # Print turn indicator + user message
            act_name = _act_for_turn(turn_num)
            print_turn_indicator(turn_num, total, act_name)
            print_user_message(text, self._current_member)

            # Flush buffered weave results before next turn
            output = self._coord.get_output_channel()
            pending = output.flush_pending_weaves()
            if pending:
                from poc.k1_poc.demo.display import print_concierge_message

                for weave_text in pending:
                    print_concierge_message(f"[background update]\n{weave_text}")

            # Process
            self._turn = turn_num - 1  # _process_turn increments
            await self._process_turn(text)

            # Delay
            if self._running:
                await asyncio.sleep(delay_s)

        print_demo_header("AUTO-PLAY COMPLETE")

    async def _run_story_demo(self, *, walkthrough: bool, fast: bool) -> None:
        """Run scripted storyline demo with act headers, anniversary demo style."""
        delay_s = 0.8 if fast else AUTO_PLAY_DELAY_S
        intro_pause_s = 0.2 if fast else 1.0
        total = max(e["turn"] for e in STORYLINE_TURNS)

        # Enable animated rendering for video recording
        self._coord.get_output_channel().set_animated(True)

        print_demo_header(
            "ONE ORDINARY DAY",
            "A Smith Family Morning",
            f"A {total}-Turn FamilyOS Demo",
        )
        print_system_message(f"Session started: k1-demo-{id(self)}")
        print_system_message("ConciergeFSM initialized as orchestrator")
        print_system_message(f"LLM adapter: {type(self._coord.model).__name__}")
        print_system_message("Scoreboard + Narrative Tracking initialized")
        print_system_message(f"Walkthrough: {'ON' if walkthrough else 'OFF'}")

        await asyncio.sleep(intro_pause_s)

        current_act = ""

        for entry in STORYLINE_TURNS:
            if not self._running:
                break

            turn_num = entry["turn"]
            device = entry["device"]
            text = entry["text"]
            act = _act_for_turn(turn_num)

            if act != current_act:
                current_act = act
                act_range = _act_turn_range(turn_num)
                print_act_header(current_act, act_range)

            self._switch_device(device)

            # Turn indicator with progress bar
            print_turn_indicator(turn_num, total, current_act)

            # User message in MEMBER: style
            print_user_message(text, self._current_member)

            # Flush buffered weave results before next turn
            output = self._coord.get_output_channel()
            pending = output.flush_pending_weaves()
            if pending:
                from poc.k1_poc.demo.display import print_concierge_message

                for weave_text in pending:
                    print_concierge_message(f"[background update]\n{weave_text}")

            if walkthrough:
                await self._async_input("  Press Enter to run this turn...")

            self._turn = turn_num - 1
            await self._process_turn(text)

            if self._running and not walkthrough:
                await asyncio.sleep(delay_s)

        print_demo_complete()

    # -----------------------------------------------------------------
    # Special commands
    # -----------------------------------------------------------------

    async def _handle_command(self, raw: str) -> bool:
        """Handle / commands.  Returns False if loop should exit."""
        parts = raw.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/quit" or cmd == "/exit":
            print("  Shutting down...")
            return False

        elif cmd == "/status":
            self._print_status()

        elif cmd == "/switch":
            if arg:
                self._switch_by_name(arg.strip().lower())
            else:
                print("  Usage: /switch <alex|jordan|nana|hub>")

        elif cmd == "/turn":
            if arg.isdigit():
                self._turn = int(arg)
                print(f"  Turn set to {self._turn}")
            else:
                print(f"  Current turn: {self._turn}")

        elif cmd == "/replay":
            turn_num = int(arg) if arg.isdigit() else self._turn
            await self._replay_turn(turn_num)

        elif cmd == "/timeline":
            self._print_timeline(int(arg) if arg.isdigit() else 20)

        elif cmd == "/help":
            self._print_help()

        else:
            print(f"  Unknown command: {cmd}. Type /help for list.")

        return True

    # -----------------------------------------------------------------
    # Device identity
    # -----------------------------------------------------------------

    def _parse_device_prefix(self, raw: str) -> tuple[str, str]:
        """Parse [device] prefix from input. Returns (device_id, text)."""
        if raw.startswith("[") and "]" in raw:
            bracket_end = raw.index("]")
            name = raw[1:bracket_end].strip().lower()
            text = raw[bracket_end + 1 :].strip()
            device_id = MEMBER_TO_DEFAULT_DEVICE.get(name)
            if device_id:
                return device_id, text
            # Try direct device id
            if name in DEVICE_REGISTRY:
                return name, text
        return "", raw

    def _switch_device(self, device_id: str) -> None:
        if device_id in DEVICE_REGISTRY:
            self._current_device = device_id
            self._current_member = resolve_member(device_id)
        elif device_id in MEMBER_TO_DEFAULT_DEVICE:
            self._current_device = MEMBER_TO_DEFAULT_DEVICE[device_id]
            self._current_member = resolve_member(self._current_device)

    def _switch_by_name(self, name: str) -> None:
        device = MEMBER_TO_DEFAULT_DEVICE.get(name)
        if device:
            self._switch_device(device)
            print(f"  Switched to {self._current_member} " f"({self._current_device})")
        else:
            print(f"  Unknown member: {name}")
            print(f"  Available: {', '.join(MEMBER_TO_DEFAULT_DEVICE.keys())}")

    # -----------------------------------------------------------------
    # Replay
    # -----------------------------------------------------------------

    async def _replay_turn(self, turn_num: int) -> None:
        """Replay a specific storyline turn."""
        for entry in STORYLINE_TURNS:
            if entry["turn"] == turn_num:
                self._switch_device(entry["device"])
                print(f"\n  Replaying turn {turn_num}: {entry['text']}")
                self._turn = turn_num - 1
                await self._process_turn(entry["text"])
                return
        print(f"  No storyline turn {turn_num} found.")

    # -----------------------------------------------------------------
    # Display helpers
    # -----------------------------------------------------------------

    def _print_welcome(self) -> None:
        print_demo_header(
            "ONE ORDINARY DAY",
            "K1 Concierge POC -- Interactive",
        )
        print_system_message(f"Family: {self._coord.family_profile.get('family_name', '?')}")
        print_system_message(f"Member: {self._current_member}")
        print_system_message(f"Device: {self._current_device}")
        print_system_message(f"LLM: {type(self._coord.model).__name__}")
        print_system_message("Type a message to talk to FamilyOS.")
        print_system_message("Prefix with [jordan] or [alex] to switch speaker.")
        print_system_message("Type /help for commands.")

    def _print_help(self) -> None:
        print("\n  Commands:")
        print("    /quit           Exit the demo")
        print("    /status         Show system status")
        print("    /switch <name>  Switch active member (alex, jordan, nana, hub)")
        print("    /turn [n]       Show or set current turn number")
        print("    /replay <n>     Replay storyline turn N")
        print("    /timeline [n]   Show last N timeline entries (default 20)")
        print("    /help           Show this help")
        print()
        print("  Device prefix: [alex] hello -> sends as Alex")
        print()

    def _print_status(self) -> None:
        report = self._coord.get_status_report()
        print("\n  --- System Status ---")
        print(f"  Ready:           {report['system_ready']}")
        print(f"  Phases:          {report['phases_completed']}")
        print(f"  Startup:         {report['total_startup_s']}s")
        print(f"  Current turn:    {self._turn}")
        print(f"  Current member:  {self._current_member}")
        print(f"  Current device:  {self._current_device}")
        if self._coord.fsm:
            print(f"  FSM state:       {self._coord.fsm.state.name}")
        print(f"  Timeline entries: {report['timeline_count']}")
        for name, val in report.get("components", {}).items():
            print(f"    {name}: {val}")
        print()

    def _print_timeline(self, n: int = 20) -> None:
        entries = self._coord.timeline[-n:]
        print(f"\n  --- Last {len(entries)} Timeline Entries ---")
        for e in entries:
            print(
                f"  {e.elapsed_ms:>10.1f}ms | {e.phase:<10} | "
                f"{e.component:<12} | {e.summary[:60]}"
            )
        print()

    # -----------------------------------------------------------------
    # Async input helper
    # -----------------------------------------------------------------

    @staticmethod
    async def _async_input(prompt: str) -> str:
        """Non-blocking stdin read."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: input(prompt))
