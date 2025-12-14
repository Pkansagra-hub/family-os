"""
ChatCLI - Interactive command-line interface for Concierge PoC.

Features:
- Real-time event streaming from ConciergeAgent
- Pretty printing with colors and progress bars
- Special commands: /help, /clear, /exit, /metrics, /demo
- Demo mode with auto-typing for presentations

Usage:
    python -m backend.cli.chat

Research basis:
- Terminal UI/UX patterns for conversational AI
- Real-time streaming for responsive feel
- Demonstration scenarios for stakeholder presentations
"""

import asyncio
import time
from typing import Any, Dict

from backend.agents.concierge import ConciergeAgent
from backend.cli.display import DisplayHelper
from backend.models.conversation_state import ConversationState


class ChatCLI:
    """Interactive CLI chat interface for Concierge PoC."""

    # Demo scenario with (message, delay_before_next) tuples
    DEMO_SCRIPT = [
        ("milk is making me sick", 3.0),
        ("pain in left side, maybe 7/10", 2.0),
    ]

    def __init__(self, concierge: ConciergeAgent, display: DisplayHelper):
        """
        Initialize CLI.

        Args:
            concierge: ConciergeAgent instance
            display: DisplayHelper for pretty printing
        """
        self.concierge = concierge
        self.display = display
        self.last_metrics: Dict[str, Any] = {}
        self.conversation_history = []
        self.running = True
        # Create persistent conversation state for this CLI session
        self.conversation_state = ConversationState(
            user_id="demo_user_001",
            conversation_id="demo_conversation_001",
        )

    async def start(self) -> None:
        """Start the CLI chat interface."""
        try:
            self.display.print_welcome()

            while self.running:
                try:
                    # Get user input
                    user_input = await self._get_user_input()

                    if not user_input.strip():
                        continue

                    # Handle commands
                    if user_input.startswith("/"):
                        if await self._handle_command(user_input):
                            continue

                    # Process regular message
                    await self._process_message(user_input)

                except KeyboardInterrupt:
                    self.display.print_error("Interrupted by user")
                    break
                except Exception as e:
                    self.display.print_error(f"Error: {str(e)}")

            self.display.print_goodbye()

        except Exception as e:
            self.display.print_error(f"Fatal error: {str(e)}")

    async def _get_user_input(self) -> str:
        """
        Get user input from stdin (async).

        Returns:
            User input string
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: input("\n[bold white]You:[/bold white] ").strip()
        )

    async def _handle_command(self, command: str) -> bool:
        """
        Handle special commands.

        Args:
            command: Command string starting with /

        Returns:
            True if command was handled, False if not
        """
        cmd = command.lower().strip()

        if cmd in ["/exit", "/quit"]:
            self.running = False
            return True

        elif cmd == "/help":
            self.display.print_help()
            return True

        elif cmd == "/clear":
            self.conversation_history = []
            self.display.print_message("Conversation history cleared.", "System")
            return True

        elif cmd == "/metrics":
            if self.last_metrics:
                self.display.print_metrics(self.last_metrics)
            else:
                self.display.print_message(
                    "No metrics available yet. Send a message first.", "System"
                )
            return True

        elif cmd == "/demo":
            await self._run_demo()
            return True

        else:
            self.display.print_error(f"Unknown command: {cmd}. Type /help for available commands.")
            return True

    async def _process_message(self, user_message: str) -> None:
        """
        Process user message through ConciergeAgent.

        Args:
            user_message: User input message
        """
        try:
            # Record user message
            self.display.print_message(user_message, "You")
            self.conversation_history.append({"role": "user", "content": user_message})

            # Track start time
            turn_start = time.time()

            # Process through concierge with conversation state
            result = await self.concierge.handle_message(user_message, self.conversation_state)

            # Display reactive response
            if result.get("reactive_response"):
                self.display.print_message(result["reactive_response"], "Agent")

            # Display proactive prompts
            proactive_prompts = result.get("proactive_prompts", [])
            for prompt in proactive_prompts:
                self.display.print_proactive(prompt.text)

            # Display combined response
            if result.get("combined_response"):
                self.display.print_message(result["combined_response"], "Agent")

            # Record final time
            turn_duration = (time.time() - turn_start) * 1000  # ms

            # Store metrics for /metrics command
            metrics = result.get("metrics", {})
            self.last_metrics = {
                "total_latency_ms": metrics.get("total_time_ms", turn_duration),
                "reactive_latency_ms": metrics.get("reactive_time_ms", 0),
                "specialist_latency_ms": metrics.get("specialist_time_ms", 0),
                "proactive_count": metrics.get("proactive_count", 0),
                "timestamp": time.time(),
            }

            # Add agent response to history
            self.conversation_history.append(
                {"role": "assistant", "content": result.get("combined_response", "")}
            )

        except Exception as e:
            self.display.print_error(f"Failed to process message: {str(e)}")

    async def _run_demo(self) -> None:
        """Run demo scenario with auto-typed messages."""
        self.display.print_section_divider("RUNNING GERD DEMO SCENARIO")
        self.display.print_message(
            "Running demo scenario: GERD trigger discovery with contradiction detection",
            "System",
        )
        self.display.print_section_divider()

        for message, delay_after in self.DEMO_SCRIPT:
            # Show message being typed
            self.display.print_message(message, "You")
            self.conversation_history.append({"role": "user", "content": message})

            # Process through concierge with conversation state
            try:
                turn_start = time.time()

                result = await self.concierge.handle_message(message, self.conversation_state)

                # Display reactive response
                if result.get("reactive_response"):
                    self.display.print_message(result["reactive_response"], "Agent")

                # Display proactive prompts
                proactive_prompts = result.get("proactive_prompts", [])
                for prompt in proactive_prompts:
                    self.display.print_proactive(prompt.text)

                # Display combined response
                if result.get("combined_response"):
                    self.display.print_message(result["combined_response"], "Agent")

                turn_duration = (time.time() - turn_start) * 1000
                metrics = result.get("metrics", {})

                # Store metrics
                self.last_metrics = {
                    "total_latency_ms": metrics.get("total_time_ms", turn_duration),
                    "reactive_latency_ms": metrics.get("reactive_time_ms", 0),
                    "specialist_latency_ms": metrics.get("specialist_time_ms", 0),
                    "proactive_count": metrics.get("proactive_count", 0),
                    "timestamp": time.time(),
                }

                self.conversation_history.append(
                    {"role": "assistant", "content": result.get("combined_response", "")}
                )

                # Wait before next message
                if delay_after > 0:
                    self.display.print_section_divider(f"Continuing in {delay_after:.1f}s...")
                    await asyncio.sleep(delay_after)

            except Exception as e:
                self.display.print_error(f"Demo error: {str(e)}")
                break

        self.display.print_section_divider("DEMO COMPLETE")
        self.display.print_message(
            "Demo scenario finished. Try /metrics to see performance data or ask your own questions.",
            "System",
        )
