"""
SessionState CLI - Command-Line Interface for Standalone Testing
=================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.5 SessionStateFactory and Standalone Mode
ISSUE: 3.5.4

PURPOSE:
    CLI for manual testing and debugging of SessionState in standalone mode.
    Useful for development, debugging, and demonstrating functionality.

COMMANDS:
    start       Start a new session or resume existing
    stop        Stop the current session (with optional checkpoint)
    status      Show session status and health
    snapshot    Display current session snapshot
    mutate      Apply a mutation to a section
    restore     Restore session from checkpoint
    sections    List all sections with sizes
    checkpoint  Create a manual checkpoint
    demo        Run interactive demo

USAGE:
    python -m k1.sessionstate.cli start --session-id dev-001
    python -m k1.sessionstate.cli status
    python -m k1.sessionstate.cli mutate beliefs_active add '{"subject": "user"}'
    python -m k1.sessionstate.cli snapshot
    python -m k1.sessionstate.cli stop

INTERACTIVE MODE:
    python -m k1.sessionstate.cli demo
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

from .factory import SessionStateFactory, create_standalone
from .manager import SessionStateManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# CLI STATE MANAGEMENT
# =============================================================================


class CLIState:
    """
    Manages CLI session state across commands.

    Uses a state file to persist session ID and DB path between invocations.
    """

    STATE_FILE = Path.home() / ".familyos" / "k1" / "cli_state.json"

    def __init__(self) -> None:
        self._manager: Optional[SessionStateManager] = None
        self._session_id: Optional[str] = None
        self._db_path: Optional[Path] = None

    def load(self) -> None:
        """Load state from file."""
        if self.STATE_FILE.exists():
            try:
                data = json.loads(self.STATE_FILE.read_text())
                self._session_id = data.get("session_id")
                db_path = data.get("db_path")
                if db_path:
                    self._db_path = Path(db_path)
            except (json.JSONDecodeError, KeyError):
                pass

    def save(self) -> None:
        """Save state to file."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "session_id": self._session_id,
            "db_path": str(self._db_path) if self._db_path else None,
        }
        self.STATE_FILE.write_text(json.dumps(data, indent=2))

    def clear(self) -> None:
        """Clear saved state."""
        if self.STATE_FILE.exists():
            self.STATE_FILE.unlink()
        self._session_id = None
        self._db_path = None

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    @property
    def db_path(self) -> Optional[Path]:
        return self._db_path

    @db_path.setter
    def db_path(self, value: Path) -> None:
        self._db_path = value

    def get_manager(self) -> Optional[SessionStateManager]:
        """Get or create manager for current session."""
        if self._manager is None and self._session_id:
            self._manager = create_standalone(
                session_id=self._session_id,
                db_path=self._db_path,
            )
        return self._manager


# Global CLI state
cli_state = CLIState()


# =============================================================================
# COMMAND IMPLEMENTATIONS
# =============================================================================


def cmd_start(args: argparse.Namespace) -> int:
    """Start a new session or resume existing."""
    cli_state.load()

    session_id = args.session_id or cli_state.session_id
    db_path = Path(args.db_path) if args.db_path else cli_state.db_path

    if not session_id:
        # Generate new session ID
        import uuid

        session_id = f"cli-{uuid.uuid4().hex[:8]}"

    print(f"Starting session: {session_id}")
    if db_path:
        print(f"Database: {db_path}")

    # Create manager
    manager = create_standalone(
        session_id=session_id,
        db_path=db_path,
        checkpoint_interval_s=args.checkpoint_interval,
    )

    # Start with optional restore
    result = manager.start(restore_if_exists=args.restore)

    if result.success:
        print("Session started successfully")
        print(f"  Restored from: {result.restore_source.name}")
        if result.sections_restored:
            print(f"  Sections restored: {', '.join(result.sections_restored)}")

        # Save state for subsequent commands
        cli_state.session_id = session_id
        cli_state.db_path = db_path
        cli_state.save()

        # Show initial status
        _print_status(manager)
        return 0
    else:
        print(f"Failed to start session: {result.error}")
        return 1


def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the current session."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    # Need to start before we can stop (to get into RUNNING state)
    manager.start(restore_if_exists=True)

    print(f"Stopping session: {cli_state.session_id}")
    result = manager.stop(checkpoint_before_stop=args.checkpoint)

    if result.success:
        print("Session stopped successfully")
        if result.checkpoint_created:
            print(f"  Checkpoint created: {result.checkpoint_id}")
            print(f"  Duration: {result.duration_ms:.1f}ms")

        if args.clear:
            cli_state.clear()
            print("Session state cleared")
        return 0
    else:
        print(f"Failed to stop session: {result.error}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show session status and health."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    # Start to load state
    manager.start(restore_if_exists=True)
    _print_status(manager)
    manager.stop(checkpoint_before_stop=False)

    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Display current session snapshot."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    manager.start(restore_if_exists=True)

    snapshot = manager.get_snapshot()

    print("\n=== SESSION SNAPSHOT ===")
    print(f"Session ID: {snapshot.session_id}")
    print(f"State: {snapshot.state.name}")
    print(f"Total Size: {snapshot.total_size_bytes:,} bytes")
    print(f"Hot Size: {snapshot.hot_size_bytes:,} bytes")
    print(f"Warm Size: {snapshot.warm_size_bytes:,} bytes")
    print(f"Pressure Level: {snapshot.pressure_level.name}")
    print(f"Timestamp: {snapshot.timestamp_ms}")

    if args.sections:
        print("\n--- SECTIONS ---")
        for section_name in sorted(snapshot.sections.keys()):
            section_info = snapshot.sections[section_name]
            print(f"  {section_name}:")
            print(f"    Tier: {section_info.tier}")
            print(f"    Size: {section_info.size_bytes:,} bytes")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(snapshot.to_dict(), indent=2))

    manager.stop(checkpoint_before_stop=False)
    return 0


def cmd_mutate(args: argparse.Namespace) -> int:
    """Apply a mutation to a section."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    # Parse data as JSON
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON data: {e}")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    manager.start(restore_if_exists=True)

    print(f"Mutating {args.section}.{args.operation}...")

    try:
        result = manager.mutate(
            section=args.section,
            operation=args.operation,
            data=data,
        )

        if result.approved:
            print("Mutation approved")
            print(f"  Section: {args.section}")
            print(f"  Operation: {args.operation}")
            print(f"  Pressure: {result.pressure_level.name}")
            print(f"  Available: {result.available_bytes:,} bytes")
        else:
            print(f"Mutation rejected: {result.rejection_reason}")

    except Exception as e:
        print(f"Mutation error: {e}")
        manager.stop(checkpoint_before_stop=False)
        return 1

    manager.stop(checkpoint_before_stop=True)
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore session from checkpoint."""
    cli_state.load()

    session_id = args.session_id or cli_state.session_id
    if not session_id:
        print("No session ID specified. Use --session-id or start a session first.")
        return 1

    db_path = Path(args.db_path) if args.db_path else cli_state.db_path

    print(f"Restoring session: {session_id}")

    manager = create_standalone(
        session_id=session_id,
        db_path=db_path,
    )

    result = manager.start(restore_if_exists=True)

    if result.success:
        print("Session restored successfully")
        print(f"  Source: {result.restore_source.name}")
        if result.sections_restored:
            print(f"  Sections: {', '.join(result.sections_restored)}")

        # Update CLI state
        cli_state.session_id = session_id
        cli_state.db_path = db_path
        cli_state.save()

        _print_status(manager)
        manager.stop(checkpoint_before_stop=False)
        return 0
    else:
        print(f"Failed to restore: {result.error}")
        return 1


def cmd_sections(args: argparse.Namespace) -> int:
    """List all sections with sizes."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    manager.start(restore_if_exists=True)

    print("\n=== SECTIONS ===")
    print(f"{'Section':<25} {'Tier':<8} {'Size':>10} {'Budget':>10} {'Usage':>8}")
    print("-" * 65)

    # HOT sections
    hot_sections = [
        "control",
        "beliefs_active",
        "scoreboard",
        "history_active",
        "clarifications",
        "affective_now",
        "narrative_active",
        "meta",
    ]

    # WARM sections
    warm_sections = [
        "beliefs_history",
        "history_recent",
        "persona",
        "telemetry",
    ]

    for section_name in hot_sections + warm_sections:
        try:
            section = manager.get_section(section_name)
            tier = "HOT" if section_name in hot_sections else "WARM"
            size = section.size_bytes
            budget = section.SIZE_BUDGET
            usage = (size / budget * 100) if budget > 0 else 0
            print(f"{section_name:<25} {tier:<8} {size:>10,} {budget:>10,} {usage:>7.1f}%")
        except Exception:
            print(f"{section_name:<25} {'?':<8} {'N/A':>10} {'N/A':>10} {'N/A':>8}")

    manager.stop(checkpoint_before_stop=False)
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    """Create a manual checkpoint."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    manager.start(restore_if_exists=True)

    print("Creating checkpoint...")
    result = manager.checkpoint()

    if result.success:
        print("Checkpoint created successfully")
        print(f"  Checkpoint ID: {result.checkpoint_id}")
        print(f"  Size: {result.size_bytes:,} bytes")
        print(f"  Duration: {result.duration_ms:.1f}ms")
        sla_status = "PASS" if result.met_sla else "FAIL"
        print(f"  SLA (<50ms): {sla_status}")
    else:
        print(f"Checkpoint failed: {result.error}")

    manager.stop(checkpoint_before_stop=False)
    return 0 if result.success else 1


def cmd_pressure(args: argparse.Namespace) -> int:
    """Show current pressure levels."""
    cli_state.load()

    if not cli_state.session_id:
        print("No active session. Use 'start' first.")
        return 1

    manager = create_standalone(
        session_id=cli_state.session_id,
        db_path=cli_state.db_path,
    )

    manager.start(restore_if_exists=True)

    print("\n=== PRESSURE REPORT ===")

    # Get health
    health = manager.health()

    print(f"\nOverall Pressure: {health.pressure_level.name}")
    print(f"Hot Utilization: {health.hot_utilization_pct:.1f}%")
    print(f"Warm Utilization: {health.warm_utilization_pct:.1f}%")

    # Show thresholds
    print("\nThresholds:")
    print("  NORMAL:   < 83%")
    print("  ELEVATED: 83% - 90%")
    print("  HIGH:     90% - 95%")
    print("  CRITICAL: > 95%")

    manager.stop(checkpoint_before_stop=False)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run interactive demo."""
    print("\n=== SESSIONSTATE INTERACTIVE DEMO ===\n")

    # Create standalone session
    session_id = f"demo-{int(time.time())}"
    print(f"1. Creating standalone session: {session_id}")

    manager = SessionStateFactory.create_standalone(session_id=session_id)

    # Start session
    print("\n2. Starting session...")
    result = manager.start()
    print(f"   Started: {result.success}")
    print(f"   Source: {result.restore_source.name}")

    # Show initial status
    print("\n3. Initial status:")
    _print_status(manager, indent="   ")

    # Make some mutations
    print("\n4. Making mutations...")

    # Add a belief
    print("   - Adding belief...")
    belief_result = manager.mutate(
        section="beliefs_active",
        operation="add",
        data={
            "subject": "user",
            "predicate": "prefers",
            "object": "dark mode",
            "confidence": 0.9,
        },
    )
    print(f"     Result: {'approved' if belief_result.approved else 'rejected'}")

    # Update scoreboard
    print("   - Updating scoreboard intent...")
    intent_result = manager.mutate(
        section="scoreboard",
        operation="set_intent",
        data={"intent": "demo_intent", "confidence": 0.85},
    )
    print(f"     Result: {'approved' if intent_result.approved else 'rejected'}")

    # Advance turn
    print("   - Advancing turn...")
    control = manager.get_section("control")
    control.advance_turn()
    print(f"     Turn: {control.current_turn_id}")

    # Show snapshot
    print("\n5. Session snapshot:")
    snapshot = manager.get_snapshot()
    print(f"   Total size: {snapshot.total_size_bytes:,} bytes")
    print(f"   Hot size: {snapshot.hot_size_bytes:,} bytes")
    print(f"   Warm size: {snapshot.warm_size_bytes:,} bytes")
    print(f"   Pressure: {snapshot.pressure_level.name}")

    # Checkpoint
    print("\n6. Creating checkpoint...")
    checkpoint_result = manager.checkpoint()
    print(f"   Checkpoint ID: {checkpoint_result.checkpoint_id}")
    print(f"   Duration: {checkpoint_result.duration_ms:.1f}ms")

    # Stop
    print("\n7. Stopping session...")
    stop_result = manager.stop()
    print(f"   Stopped: {stop_result.success}")

    print("\n=== DEMO COMPLETE ===\n")
    return 0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _print_status(manager: SessionStateManager, indent: str = "") -> None:
    """Print session status."""
    health = manager.health()

    print(f"\n{indent}=== SESSION STATUS ===")
    print(f"{indent}Session ID: {manager.session_id}")
    print(f"{indent}State: {manager.state.name}")
    print(f"{indent}Running: {manager.is_running}")

    print(f"\n{indent}--- Health ---")
    print(f"{indent}Healthy: {health.is_healthy}")
    print(f"{indent}Hot Utilization: {health.hot_utilization_pct:.1f}%")
    print(f"{indent}Warm Utilization: {health.warm_utilization_pct:.1f}%")
    print(f"{indent}Pressure: {health.pressure_level.name}")
    print(f"{indent}Turn Count: {health.turn_count}")
    print(f"{indent}Mutation Count: {health.mutation_count}")
    print(f"{indent}Checkpoint Count: {health.checkpoint_count}")


# =============================================================================
# ARGUMENT PARSER
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI."""
    parser = argparse.ArgumentParser(
        prog="sessionstate",
        description="SessionState CLI for standalone testing and debugging",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # start command
    start_parser = subparsers.add_parser("start", help="Start a new session")
    start_parser.add_argument(
        "--session-id", "-s", help="Session ID (auto-generated if not specified)"
    )
    start_parser.add_argument("--db-path", "-d", help="Database path")
    start_parser.add_argument(
        "--checkpoint-interval",
        "-c",
        type=float,
        default=30.0,
        help="Checkpoint interval in seconds (default: 30)",
    )
    start_parser.add_argument(
        "--no-restore",
        dest="restore",
        action="store_false",
        help="Don't restore from existing checkpoint",
    )

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop the current session")
    stop_parser.add_argument(
        "--no-checkpoint",
        dest="checkpoint",
        action="store_false",
        help="Don't create checkpoint before stopping",
    )
    stop_parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear session state after stopping",
    )

    # status command
    subparsers.add_parser("status", help="Show session status")

    # snapshot command
    snapshot_parser = subparsers.add_parser("snapshot", help="Display session snapshot")
    snapshot_parser.add_argument(
        "--sections",
        action="store_true",
        help="Show section details",
    )
    snapshot_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # mutate command
    mutate_parser = subparsers.add_parser("mutate", help="Apply a mutation")
    mutate_parser.add_argument("section", help="Section name (e.g., beliefs_active)")
    mutate_parser.add_argument("operation", help="Operation (e.g., add, set, remove)")
    mutate_parser.add_argument("data", help="JSON data for mutation")

    # restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from checkpoint")
    restore_parser.add_argument("--session-id", "-s", help="Session ID to restore")
    restore_parser.add_argument("--db-path", "-d", help="Database path")

    # sections command
    subparsers.add_parser("sections", help="List all sections with sizes")

    # checkpoint command
    subparsers.add_parser("checkpoint", help="Create a manual checkpoint")

    # pressure command
    subparsers.add_parser("pressure", help="Show pressure levels")

    # demo command
    subparsers.add_parser("demo", help="Run interactive demo")

    return parser


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for CLI."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to command handler
    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "snapshot": cmd_snapshot,
        "mutate": cmd_mutate,
        "restore": cmd_restore,
        "sections": cmd_sections,
        "checkpoint": cmd_checkpoint,
        "pressure": cmd_pressure,
        "demo": cmd_demo,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            return handler(args)
        except KeyboardInterrupt:
            print("\nInterrupted")
            return 130
        except Exception as e:
            print(f"Error: {e}")
            if args.verbose:
                import traceback

                traceback.print_exc()
            return 1
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
