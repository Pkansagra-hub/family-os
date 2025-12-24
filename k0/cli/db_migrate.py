"""Alembic CLI wrapper for K0 kernel migrations.

Part of Milestone 1.1.2 - Issue 1.1.2.4: Create Alembic CLI Wrapper.

This module provides a CLI wrapper around Alembic commands for K0 database
migrations. It can be used standalone or integrated with k0ctl.

Usage:
    # Standalone
    python -m k0.cli.db_migrate upgrade head
    python -m k0.cli.db_migrate downgrade -1
    python -m k0.cli.db_migrate current
    python -m k0.cli.db_migrate history
    python -m k0.cli.db_migrate revision -m "add users table"

    # Via k0ctl (after integration)
    k0ctl db upgrade head
    k0ctl db current
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def get_alembic_config():
    """Get Alembic config pointing to k0/db/alembic.ini.

    Returns:
        Alembic Config object configured for K0.

    Raises:
        FileNotFoundError: If alembic.ini is not found.
    """
    from alembic.config import Config

    # Find alembic.ini relative to this file
    config_path = Path(__file__).parent.parent / "db" / "alembic.ini"
    if not config_path.exists():
        raise FileNotFoundError(f"Alembic config not found: {config_path}")

    return Config(str(config_path))


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Apply pending migrations.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()
    revision = args.revision or "head"

    if args.dry_run:
        # Generate SQL without executing
        print(f"-- Dry run: migrations to {revision}")
        command.upgrade(cfg, revision, sql=True)
    else:
        print(f"Applying migrations to {revision}...")
        command.upgrade(cfg, revision)
        print("Migrations applied successfully.")

    return 0


def cmd_downgrade(args: argparse.Namespace) -> int:
    """Revert migrations.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()
    revision = args.revision

    print(f"Reverting to revision {revision}...")
    command.downgrade(cfg, revision)
    print("Downgrade completed.")

    return 0


def cmd_current(args: argparse.Namespace) -> int:
    """Show current revision.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()
    command.current(cfg, verbose=args.verbose)

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show migration history.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()
    command.history(cfg, verbose=args.verbose)

    return 0


def cmd_revision(args: argparse.Namespace) -> int:
    """Create a new migration.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()

    print(f"Creating migration: {args.message}")
    command.revision(
        cfg,
        message=args.message,
        autogenerate=args.autogenerate,
    )
    print("Migration created successfully.")

    return 0


def cmd_heads(args: argparse.Namespace) -> int:
    """Show current heads.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()
    command.heads(cfg, verbose=args.verbose)

    return 0


def cmd_stamp(args: argparse.Namespace) -> int:
    """Stamp the database with a revision without running migrations.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success).
    """
    from alembic import command

    cfg = get_alembic_config()

    print(f"Stamping database with revision {args.revision}...")
    command.stamp(cfg, args.revision)
    print("Stamp completed.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for db-migrate CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="k0ctl db",
        description="K0 database migration commands (Alembic wrapper)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s upgrade head          Apply all pending migrations
    %(prog)s upgrade +2            Apply next 2 migrations
    %(prog)s downgrade -1          Revert last migration
    %(prog)s downgrade 0001        Revert to revision 0001
    %(prog)s current               Show current revision
    %(prog)s history -v            Show migration history (verbose)
    %(prog)s revision -m "..."     Create new migration
        """,
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="COMMAND",
    )

    # upgrade
    up = subparsers.add_parser(
        "upgrade",
        help="Apply pending migrations",
        description="Apply database migrations up to the specified revision.",
    )
    up.add_argument(
        "revision",
        nargs="?",
        default="head",
        help="Target revision (default: head)",
    )
    up.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL without executing",
    )
    up.set_defaults(func=cmd_upgrade)

    # downgrade
    down = subparsers.add_parser(
        "downgrade",
        help="Revert migrations",
        description="Revert database migrations to the specified revision.",
    )
    down.add_argument(
        "revision",
        default="-1",
        help="Target revision (default: -1, previous)",
    )
    down.set_defaults(func=cmd_downgrade)

    # current
    cur = subparsers.add_parser(
        "current",
        help="Show current revision",
        description="Display the current revision(s) in the database.",
    )
    cur.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )
    cur.set_defaults(func=cmd_current)

    # history
    hist = subparsers.add_parser(
        "history",
        help="Show migration history",
        description="Display the history of all migrations.",
    )
    hist.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )
    hist.set_defaults(func=cmd_history)

    # heads
    heads = subparsers.add_parser(
        "heads",
        help="Show current heads",
        description="Display the current head revision(s).",
    )
    heads.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show verbose output",
    )
    heads.set_defaults(func=cmd_heads)

    # revision
    rev = subparsers.add_parser(
        "revision",
        help="Create a new migration",
        description="Generate a new migration script.",
    )
    rev.add_argument(
        "-m",
        "--message",
        required=True,
        help="Migration description",
    )
    rev.add_argument(
        "--autogenerate",
        action="store_true",
        help="Autogenerate migration from model changes",
    )
    rev.set_defaults(func=cmd_revision)

    # stamp
    stamp = subparsers.add_parser(
        "stamp",
        help="Stamp revision without migrating",
        description="Mark a revision as current without running migrations.",
    )
    stamp.add_argument(
        "revision",
        help="Revision to stamp",
    )
    stamp.set_defaults(func=cmd_stamp)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for db-migrate CLI.

    Args:
        argv: Command-line arguments (uses sys.argv if None).

    Returns:
        Exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Migration error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
