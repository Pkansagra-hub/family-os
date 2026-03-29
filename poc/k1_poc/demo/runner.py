"""
poc.k1_poc.demo.runner -- Entry point for the K1 demo.

Usage::

    python -m poc.k1_poc.demo.runner                # interactive, real LLM if key present
    python -m poc.k1_poc.demo.runner --test-mode    # force test adapter
    python -m poc.k1_poc.demo.runner --auto-play    # auto-play storyline turns
    python -m poc.k1_poc.demo.runner --story-demo   # richer scripted demo mode
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from poc.k1_poc.demo.coordinator import get_k1_demo_coordinator, reset_coordinator
from poc.k1_poc.demo.display import print_boot_splash
from poc.k1_poc.demo.interactive import InteractiveDemoLoop


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="K1 Concierge POC -- Interactive Demo Runner",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        default=False,
        help="Force TestConciergeAdapter (no API key needed)",
    )
    parser.add_argument(
        "--auto-play",
        action="store_true",
        default=False,
        help="Auto-play storyline turns from demo_storyline.md",
    )
    parser.add_argument(
        "--story-demo",
        action="store_true",
        default=False,
        help="Run scripted storyline demo with act headers and narration",
    )
    parser.add_argument(
        "--walkthrough",
        action="store_true",
        default=False,
        help="In story-demo mode, pause between turns for guided walkthrough",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=False,
        help="Reduce delays in auto-play or story-demo",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress all log output -- only show spinner, prompt, and response",
    )
    parser.add_argument(
        "--dump-timeline",
        default=None,
        metavar="FILE",
        help="Dump timeline JSON to file on exit",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()

    # Configure logging
    log_level = logging.CRITICAL if args.quiet else getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Create coordinator
    reset_coordinator()
    coordinator = get_k1_demo_coordinator(test_mode=args.test_mode)

    # Signal handling for graceful shutdown
    shutdown_requested = False
    loop_instance: InteractiveDemoLoop | None = None

    def _signal_handler(sig: int, frame: object) -> None:
        nonlocal shutdown_requested
        if not shutdown_requested:
            shutdown_requested = True
            print("\n\n  Received shutdown signal...")
            coordinator.system_ready = False
            _loop = loop_instance
            if _loop is not None:
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.ensure_future(_loop.stop()),
                )

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Boot
    print_boot_splash()
    success = await coordinator.initialize_system()

    if not success:
        print("\n  System initialization FAILED. Check logs.")
        return

    # Print startup report
    coordinator.print_startup_report()

    # Run interactive loop
    loop_instance = InteractiveDemoLoop(coordinator)
    try:
        await loop_instance.run(
            auto_play=args.auto_play,
            story_demo=args.story_demo,
            walkthrough=args.walkthrough,
            fast=args.fast,
        )
    except KeyboardInterrupt:
        pass
    finally:
        # Shutdown
        print("\n  Shutting down...")
        await coordinator.shutdown_system()

        # Dump timeline if requested
        if args.dump_timeline:
            timeline_json = coordinator.dump_timeline_json()
            with open(args.dump_timeline, "w", encoding="utf-8") as f:
                f.write(timeline_json)
            print(f"  Timeline dumped to {args.dump_timeline}")

        print("  Goodbye.\n")


if __name__ == "__main__":
    asyncio.run(main())
