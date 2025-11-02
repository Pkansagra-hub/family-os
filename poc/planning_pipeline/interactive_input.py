"""
Interactive Input Handler for Planning Pipeline PoC

This module handles user input via PowerShell for HITL clarifications.
Provides rich formatted prompts with colors, timers, and error handling.

Architecture:
- InteractiveInputHandler: Main class for prompting user
- Rich console formatting with panels and colors
- Input validation (empty, cancel, timeout)
- Response time tracking

References:
- ADR-0054d: Dialogue Repair & Clarification Pipeline
- ADR-0052: Enhanced HITL Protocols
"""

import logging
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Configure logging
logger = logging.getLogger(__name__)


class InteractiveInputHandler:
    """
    Handle user input via PowerShell for clarifications

    Provides rich formatted prompts with:
    - Yellow panels for clarification questions
    - Timer for response latency
    - Empty input handling (re-prompt)
    - Cancel keywords (cancel, quit, exit)
    - Response logging

    Usage:
        handler = InteractiveInputHandler()
        response = handler.prompt_user("What time would you like?")

        if response:
            # User provided answer
            print(f"User said: {response}")
        else:
            # User cancelled
            print("Cancelled")
    """

    def __init__(self, console: Optional[Console] = None):
        """
        Initialize InteractiveInputHandler

        Args:
            console: Optional Rich Console instance (creates new if None)
        """
        self.console = console or Console()
        self.response_times = []  # Track response times for metrics
        logger.info("InteractiveInputHandler initialized")

    def prompt_user(
        self,
        question: str,
        context: Optional[str] = None,
        allow_empty: bool = False,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        Prompt user for clarification via PowerShell

        Displays formatted prompt with rich panel, gets user input,
        handles cancel/empty responses, and tracks response time.

        Args:
            question: Clarification question to display
            context: Optional context string to display above question
            allow_empty: If True, allow empty responses
            max_retries: Max retries for empty input (default 3)

        Returns:
            User's response (str) or None if cancelled
        """
        retry_count = 0

        while retry_count < max_retries:
            # Build prompt content
            prompt_content = ""

            if context:
                prompt_content += f"[dim]{context}[/dim]\n\n"

            prompt_content += f"[yellow bold]{question}[/yellow bold]\n\n"
            prompt_content += "[dim](Type your answer, or 'cancel' to abort)[/dim]"

            # Show clarification prompt panel
            self.console.print()
            self.console.print(
                Panel(
                    prompt_content,
                    border_style="yellow",
                    title="💬 [yellow bold]Clarification Needed[/yellow bold]",
                    title_align="left",
                    padding=(1, 2),
                )
            )

            # Get user input with timer
            start_time = time.time()

            try:
                response = Prompt.ask("\n[yellow]Your answer[/yellow]", console=self.console)
            except (KeyboardInterrupt, EOFError):
                # User pressed Ctrl+C or Ctrl+D
                self.console.print("\n[red]❌ Interrupted by user[/red]")
                logger.info("User interrupted input with Ctrl+C")
                return None

            elapsed_ms = int((time.time() - start_time) * 1000)
            self.response_times.append(elapsed_ms)

            # Handle cancel keywords
            if response.lower().strip() in ["cancel", "quit", "exit", "abort"]:
                self.console.print("[red]❌ Clarification cancelled by user[/red]")
                logger.info("User cancelled clarification")
                return None

            # Handle empty input
            if not response.strip():
                if allow_empty:
                    self.console.print(f"[dim]✅ Empty response accepted ({elapsed_ms}ms)[/dim]\n")
                    logger.info("Empty response accepted")
                    return ""
                else:
                    retry_count += 1
                    if retry_count < max_retries:
                        self.console.print(
                            f"[yellow]⚠️  Empty response. "
                            f"Please provide an answer (attempt {retry_count}/{max_retries})[/yellow]"
                        )
                        logger.warning(f"Empty input, retry {retry_count}/{max_retries}")
                        continue
                    else:
                        self.console.print(
                            f"[red]❌ Too many empty responses ({max_retries}). Aborting.[/red]"
                        )
                        logger.error("Too many empty responses, aborting")
                        return None

            # Valid response received
            self.console.print(f"[dim]✅ Response received ({elapsed_ms}ms)[/dim]\n")
            logger.info(f"User response: '{response[:50]}...' ({elapsed_ms}ms)")

            return response.strip()

        # Should not reach here, but handle gracefully
        self.console.print("[red]❌ Max retries exceeded[/red]")
        logger.error("Max retries exceeded in prompt_user")
        return None

    def prompt_choice(
        self, question: str, choices: list[str], default: Optional[str] = None
    ) -> Optional[str]:
        """
        Prompt user to choose from multiple options

        Args:
            question: Question to display
            choices: List of choice strings
            default: Optional default choice

        Returns:
            Selected choice (str) or None if cancelled
        """
        # Build prompt with choices
        prompt_content = f"[yellow bold]{question}[/yellow bold]\n\n"

        for i, choice in enumerate(choices, 1):
            if default and choice.lower() == default.lower():
                prompt_content += f"  [green]{i}. {choice} [bold](default)[/bold][/green]\n"
            else:
                prompt_content += f"  {i}. {choice}\n"

        prompt_content += "\n[dim](Enter number, choice name, or 'cancel')[/dim]"

        # Show panel
        self.console.print()
        self.console.print(
            Panel(
                prompt_content,
                border_style="yellow",
                title="💬 [yellow bold]Choose an Option[/yellow bold]",
                title_align="left",
                padding=(1, 2),
            )
        )

        # Get user input
        start_time = time.time()

        try:
            response = Prompt.ask("\n[yellow]Your choice[/yellow]", console=self.console)
        except (KeyboardInterrupt, EOFError):
            self.console.print("\n[red]❌ Interrupted by user[/red]")
            return None

        elapsed_ms = int((time.time() - start_time) * 1000)
        self.response_times.append(elapsed_ms)

        # Handle cancel
        if response.lower().strip() in ["cancel", "quit", "exit"]:
            self.console.print("[red]❌ Cancelled by user[/red]")
            return None

        # Handle empty (use default)
        if not response.strip() and default:
            self.console.print(f"[dim]✅ Using default: {default} ({elapsed_ms}ms)[/dim]\n")
            return default

        # Handle numeric choice
        if response.strip().isdigit():
            choice_idx = int(response.strip()) - 1
            if 0 <= choice_idx < len(choices):
                selected = choices[choice_idx]
                self.console.print(f"[dim]✅ Selected: {selected} ({elapsed_ms}ms)[/dim]\n")
                return selected
            else:
                self.console.print(f"[red]❌ Invalid choice number: {response}[/red]")
                return None

        # Handle text match
        response_lower = response.strip().lower()
        for choice in choices:
            if choice.lower() == response_lower or choice.lower().startswith(response_lower):
                self.console.print(f"[dim]✅ Selected: {choice} ({elapsed_ms}ms)[/dim]\n")
                return choice

        # No match
        self.console.print(f"[red]❌ Invalid choice: {response}[/red]")
        return None

    def show_info(self, message: str, title: str = "ℹ️  Info"):
        """Show informational message in blue panel"""
        self.console.print()
        self.console.print(
            Panel(
                f"[cyan]{message}[/cyan]",
                border_style="cyan",
                title=f"[cyan bold]{title}[/cyan bold]",
                title_align="left",
            )
        )

    def show_warning(self, message: str, title: str = "⚠️  Warning"):
        """Show warning message in yellow panel"""
        self.console.print()
        self.console.print(
            Panel(
                f"[yellow]{message}[/yellow]",
                border_style="yellow",
                title=f"[yellow bold]{title}[/yellow bold]",
                title_align="left",
            )
        )

    def show_error(self, message: str, title: str = "❌ Error"):
        """Show error message in red panel"""
        self.console.print()
        self.console.print(
            Panel(
                f"[red]{message}[/red]",
                border_style="red",
                title=f"[red bold]{title}[/red bold]",
                title_align="left",
            )
        )

    def show_success(self, message: str, title: str = "✅ Success"):
        """Show success message in green panel"""
        self.console.print()
        self.console.print(
            Panel(
                f"[green]{message}[/green]",
                border_style="green",
                title=f"[green bold]{title}[/green bold]",
                title_align="left",
            )
        )

    def get_response_time_stats(self) -> dict:
        """
        Get statistics about user response times

        Returns:
            Dict with avg, min, max, count
        """
        if not self.response_times:
            return {"count": 0, "avg_ms": 0, "min_ms": 0, "max_ms": 0}

        return {
            "count": len(self.response_times),
            "avg_ms": sum(self.response_times) / len(self.response_times),
            "min_ms": min(self.response_times),
            "max_ms": max(self.response_times),
        }


if __name__ == "__main__":
    # Interactive demo/test
    print("InteractiveInputHandler demo")
    print("=" * 50)

    handler = InteractiveInputHandler()

    # Test 1: Basic prompt
    handler.show_info("Testing basic prompt functionality")
    response = handler.prompt_user("What is your name?")
    if response:
        handler.show_success(f"Got response: {response}")
    else:
        handler.show_warning("No response (cancelled)")

    # Test 2: Multiple choice
    handler.show_info("Testing multiple choice prompt")
    choice = handler.prompt_choice(
        "How would you like to proceed?", ["Simplify", "Rephrase", "Cancel"], default="Simplify"
    )
    if choice:
        handler.show_success(f"Selected: {choice}")
    else:
        handler.show_warning("No choice (cancelled)")

    # Test 3: Show stats
    stats = handler.get_response_time_stats()
    handler.show_info(
        f"Response time stats:\n"
        f"  Count: {stats['count']}\n"
        f"  Average: {stats['avg_ms']:.0f}ms\n"
        f"  Min: {stats['min_ms']}ms\n"
        f"  Max: {stats['max_ms']}ms",
        title="📊 Statistics",
    )

    print("\n" + "=" * 50)
    print("✅ Demo complete!")
    print("✅ Demo complete!")
