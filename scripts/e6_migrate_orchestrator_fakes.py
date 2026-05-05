"""E6.M1.6 migration: strip ``emit_hil_request`` stubs from test fakes.

Removes the fake ``async def emit_hil_request(...)`` method definition
from each ``Fake*DeltaPort``-style class in tests/k1/orchestrator/, since
``IDeltaEmitPort`` no longer declares that method (E6.M1.5).

The block to delete is detected by:
  * a line starting with ``    async def emit_hil_request(``
  * the line(s) immediately following that are part of the same indented
    block (until a blank line followed by next `def`/class).

Usage:
    python scripts/e6_migrate_orchestrator_fakes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = REPO_ROOT / "tests" / "k1" / "orchestrator"

TARGETS = [
    "test_workflow_supervisor.py",
    "test_workflow_compiler.py",
    "test_sqlite_workflow_adapter.py",
    "test_mcp_connector.py",
    "test_gap_detector.py",
    "test_dag_executor_execute.py",
    "test_dag_executor_cancel_comp_wal.py",
    "test_admin_api.py",
]

def strip_one(text: str) -> tuple[str, int]:
    """Remove every block whose first line is ``async def emit_hil_request(...)``.

    Treats the block as: the signature line + every following line that is
    blank OR indented strictly deeper than the signature line. Stops at the
    first non-blank line indented at-or-above the signature.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("async def emit_hil_request("):
            sig_indent = len(line) - len(stripped)
            # Drop trailing blank lines already in `out` for cleanliness.
            while out and out[-1].strip() == "":
                out.pop()
                # Keep one blank for class spacing
                out.append("\n")
                break
            i += 1
            # Consume body
            while i < len(lines):
                body_line = lines[i]
                body_stripped = body_line.lstrip()
                if body_line.strip() == "":
                    i += 1
                    continue
                body_indent = len(body_line) - len(body_stripped)
                if body_indent > sig_indent:
                    i += 1
                    continue
                break
            removed += 1
            continue
        out.append(line)
        i += 1
    return "".join(out), removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total = 0
    for name in TARGETS:
        path = TARGET_DIR / name
        if not path.exists():
            print(f"SKIP (missing): {name}")
            continue
        original = path.read_text(encoding="utf-8")
        new_text, n = strip_one(original)
        if n == 0:
            print(f"NO-CHANGE: {name}")
            continue
        total += n
        if args.dry_run:
            print(f"WOULD-EDIT: {name} (-{n} block)")
        else:
            path.write_text(new_text, encoding="utf-8")
            print(f"EDITED: {name} (-{n} block)")
    print(f"\nTotal blocks {'would be ' if args.dry_run else ''}removed: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
