"""Shared gate infrastructure: CLI parsing, timing, outcome reporting.

Each gate calls :func:`run_gate` with its name + a callable that returns a
list of violation strings (each string is a human-readable offending line
that will be printed verbatim to stdout). Empty list = clean.

The harness:

* Times the body call.
* Prints ``[<gate-name>] <outcome> (<n> violations) in <duration_ms> ms``
  to stderr.
* Prints each violation line to stdout (so subprocess capture sees them).
* Returns the process exit code (0 clean, 1 dirty unless ``--warn-only``).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Sequence


def parse_common_args(name: str, argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=f"tooling.ci.gates.{name}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fail-on-violation",
        dest="fail_on_violation",
        action="store_true",
        default=True,
        help="Exit 1 on any violation (default).",
    )
    mode.add_argument(
        "--warn-only",
        dest="fail_on_violation",
        action="store_false",
        help="Print violations but exit 0.",
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help="Override repository root (default: 2 parents up from this module).",
    )
    return parser.parse_args(argv)


def run_gate(
    name: str,
    body: Callable[[argparse.Namespace], list[str]],
    argv: Sequence[str] | None = None,
) -> int:
    """Run ``body`` and report timing + outcome.

    ``body`` returns a list of violation strings. The harness handles all
    I/O. The body MUST NOT print to stderr/stdout itself.
    """
    args = parse_common_args(name, argv)
    started = time.perf_counter()
    try:
        violations = body(args)
    except Exception as exc:  # gate crash: still report cleanly
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(
            f"[{name}] CRASH ({type(exc).__name__}: {exc}) in {elapsed_ms} ms",
            file=sys.stderr,
        )
        return 2  # distinct from violation; CI surfaces this differently

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    n = len(violations)
    if n == 0:
        print(f"[{name}] OK (0 violations) in {elapsed_ms} ms", file=sys.stderr)
        return 0

    for line in violations:
        print(line)
    if args.fail_on_violation:
        print(f"[{name}] FAIL ({n} violation(s)) in {elapsed_ms} ms", file=sys.stderr)
        return 1
    print(f"[{name}] WARN ({n} violation(s)) in {elapsed_ms} ms", file=sys.stderr)
    return 0
