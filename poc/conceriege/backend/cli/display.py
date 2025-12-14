"""
Pretty printing helper for CLI chat interface.

Uses rich library for styling:
- Green text for agent messages
- Yellow italic text for proactive prompts
- Blue progress bars with emojis
- Red text for errors
- Tables for metrics
"""

from typing import Any, Dict

from rich.console import Console
from rich.table import Table


class DisplayHelper:
    """Helper for pretty printing CLI output using rich library."""

    def __init__(self):
        """Initialize rich console."""
        self.console = Console()

    def print_welcome(self) -> None:
        """Print welcome banner with instructions."""
        banner = """
╔══════════════════════════════════════════════════════════════╗
║          Welcome to Concierge PoC - Chat Interface          ║
╚══════════════════════════════════════════════════════════════╝

Commands:
  /help    - Show this message
  /clear   - Clear conversation history
  /exit    - Exit CLI
  /quit    - Exit CLI
  /metrics - Show performance metrics
  /demo    - Run GERD demo scenario

Example queries:
  - "milk is making me sick"
  - "I'm feeling anxious lately"
  - "reduce my GERD symptoms"

Type your message and press Enter to start.
"""
        self.console.print(banner)

    def print_message(self, text: str, sender: str = "Agent") -> None:
        """
        Print agent or user message.

        Args:
            text: Message text
            sender: "Agent" or "You"
        """
        if sender == "Agent":
            colored_sender = f"[bold green]{sender}[/bold green]:"
        else:
            colored_sender = f"[bold white]{sender}[/bold white]:"

        self.console.print(f"\n{colored_sender} {text}\n")

    def print_proactive(self, text: str) -> None:
        """
        Print proactive prompt (yellow, italic).

        Args:
            text: Proactive prompt text
        """
        self.console.print(f"[yellow italic]💡 Proactive: {text}[/yellow italic]\n")

    def print_progress(self, percent: int, message: str) -> None:
        """
        Print progress update.

        Args:
            percent: Progress percentage (0-100)
            message: Progress message with emoji
        """
        # Create progress bar
        bar_length = 20
        filled = int(bar_length * percent / 100)
        bar = "━" * filled + "─" * (bar_length - filled)

        progress_text = f"[{percent:3d}%] {bar} {message}"
        self.console.print(progress_text)

    def print_error(self, text: str) -> None:
        """
        Print error message (red).

        Args:
            text: Error message
        """
        self.console.print(f"\n[bold red]❌ Error:[/bold red] {text}\n")

    def print_metrics(self, metrics: Dict[str, Any]) -> None:
        """
        Print performance metrics as table.

        Args:
            metrics: Dictionary of metric name -> value
        """
        table = Table(title="Performance Metrics", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")

        # Format metrics
        for key, value in metrics.items():
            # Format key: snake_case -> Title Case
            display_key = key.replace("_", " ").title()

            # Format value
            if isinstance(value, float):
                if key.endswith("_ms"):
                    display_value = f"{value:.0f}ms"
                elif key.endswith("_cost"):
                    display_value = f"${value:.4f}"
                else:
                    display_value = f"{value:.2f}"
            else:
                display_value = str(value)

            table.add_row(display_key, display_value)

        self.console.print("\n")
        self.console.print(table)
        self.console.print()

    def print_help(self) -> None:
        """Print help message with all commands."""
        help_text = """
Available Commands:

  /help         - Show this message
  /clear        - Clear conversation history
  /exit, /quit  - Exit CLI
  /metrics      - Show performance metrics from last turn
  /demo         - Run GERD demo scenario (auto-types messages)

Navigation:
  - Type your message and press Enter to send
  - Use Ctrl+C to interrupt long-running operations
  - Use /clear to start fresh conversation

Examples:
  "milk is making me sick"
  "I'm feeling really anxious"
  "reduce my GERD symptoms"

Demo Scenarios:
  - GERD contradiction: User says "milk", specialist finds "coffee"
  - Proactive fills gaps: System asks clarifying questions
  - Progress tracking: Real-time updates from specialist
"""
        self.console.print(help_text)

    def print_section_divider(self, title: str = "") -> None:
        """Print a visual divider."""
        if title:
            self.console.print(f"\n[dim]─── {title} ───[/dim]\n")
        else:
            self.console.print("\n[dim]─" * 30 + "[/dim]\n")

    def print_goodbye(self) -> None:
        """Print goodbye message."""
        self.console.print("\n[bold green]Thank you for using Concierge PoC![/bold green]\n")
        self.console.print("\n[bold green]Thank you for using Concierge PoC![/bold green]\n")
