"""Kernel runner: one-command standalone startup.

Usage:
    python -m k1.concierge.kernel.runner
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from .bootstrap import KernelConfig, start_kernel, stop_kernel


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Concierge kernel (independent of demo)")
    parser.add_argument("--test-mode", action="store_true", default=False, help="Use test adapter")
    parser.add_argument(
        "--unordered", action="store_true", default=False, help="Disable ordered bus"
    )
    parser.add_argument(
        "--session-mode",
        choices=["standalone", "testing"],
        default="standalone",
        help="SessionStateFactory mode",
    )
    parser.add_argument(
        "--tool-tier",
        choices=["LOW", "MEDIUM", "HIGH", "CRISIS"],
        default="LOW",
        help="Default tool dispatcher tier",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = KernelConfig(
        ordered_bus=not args.unordered,
        test_mode=args.test_mode,
        session_mode=args.session_mode,
        tool_tier=args.tool_tier,
    )

    runtime = await start_kernel(cfg)
    print("\nKernel started. Press Ctrl+C to stop.\n")

    stop_event = asyncio.Event()

    def _request_stop(_sig: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    try:
        await stop_event.wait()
    finally:
        await stop_kernel(runtime)
        print("\nKernel stopped.\n")


if __name__ == "__main__":
    asyncio.run(_run())
