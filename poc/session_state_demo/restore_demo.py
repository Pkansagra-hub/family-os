"""
Restore Demo - Shows checkpoint recovery
==========================================

Demonstrates restoring from a previous checkpoint.

Run scripted_demo.py first to create a checkpoint, then run this.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.bridge import SessionLLMBridge  # noqa: E402
from poc.session_state_demo.config import get_config  # noqa: E402
from poc.session_state_demo.display import (  # noqa: E402
    print_header,
    print_info,
    print_section_data,
    print_snapshot,
    print_stats,
)


def main():
    """Show restore from checkpoint."""
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    print_header("SESSION STATE RESTORE DEMO")
    print_info("Restoring from previous checkpoint...")

    # Use same session ID as scripted demo
    bridge = SessionLLMBridge(
        session_id=config.session_id + "-scripted",
        db_path=str(config.db_path),
        restore_on_start=True,  # Will restore!
    )

    success, msg = bridge.start()
    print_info(msg)

    print()
    print("=" * 60)
    print("RESTORED STATE")
    print("=" * 60)

    print_snapshot(bridge.get_snapshot())
    print_stats(bridge.get_stats())

    print()
    print("--- Restored History ---")
    print_section_data("history_active", bridge.get_section_data("history_active"))

    print()
    print("--- Restored Beliefs ---")
    print_section_data("beliefs_active", bridge.get_section_data("beliefs_active"))

    print()
    print("--- Restored Persona ---")
    print_section_data("persona", bridge.get_section_data("persona"))

    # Clean stop
    bridge.stop(checkpoint_before_stop=False)
    print_info("Session stopped (no new checkpoint)")

    print_header("RESTORE DEMO COMPLETE")
    print_info("All state was recovered from the SQLite checkpoint!")


if __name__ == "__main__":
    main()
