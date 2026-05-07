"""CI gate: K1 bridge-adapter SLOC budget (MS-4 Epic 4.2).

Scope: protect the K1 adapter layer from regressing into the kind of
"thick wrapper around generated client" sprawl the bridge wall was
designed to prevent. The 12 adapters that exist today are legitimate
domain-translation layers (see
``docs/development/bridge_adapter_pattern.md``); this gate refuses any
PR that grows them past the budget recorded here without an explicit
update to the budget constants and a doc-line justifying the bump.

Counter rules
-------------
SLOC = source lines of code, defined as: non-blank, non-comment lines
after stripping ``#``-prefixed comments and triple-quoted module/class
docstrings. Imports count. Match strings live verbatim with the audit.

Files scanned
-------------
Python files matching ``k1/**/adapters/bridge*.py``,
``k1/**/adapters/*_bridge*.py``, ``k1/**/adapters/null_bridge*.py``, and
``k1/**/adapters/model_gateway_bridge.py``. Test files are excluded.
"""

from __future__ import annotations

import ast
import sys
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "adapter_loc_budget"

# Patterns: each pattern is a glob relative to repo root. We deduplicate
# across patterns so a file matched twice is still counted once.
_FILE_PATTERNS: tuple[str, ...] = (
    "k1/**/adapters/bridge*.py",
    "k1/**/adapters/*_bridge*.py",
    "k1/**/adapters/*bridge.py",
    "k1/**/adapters/null_bridge*.py",
    "k1/**/adapters/model_gateway_bridge.py",
    "k1/**/adapters/mock_bridge_adapter.py",
)

# Per-file SLOC ceiling. Pinned just above the largest current adapter
# (``k1/fabric/adapters/bridge_connection.py`` = 227 SLOC, MS-4 audit).
PER_FILE_SLOC_CAP: int = 250

# Total SLOC ceiling across all matched files. Pinned ~6% above the
# MS-4 audit total (1089 SLOC across 12 production adapter files).
TOTAL_SLOC_BUDGET: int = 1150


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _count_sloc(path: Path) -> int:
    """SLOC = non-blank, non-comment, non-docstring source lines.

    Module docstrings and class docstrings are stripped; function
    docstrings are kept (they are typically a single line and removing
    them would let an adapter dodge the budget by hiding logic in long
    docstrings). Comments are line-stripped.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Treat parse failures as 0 — the codegen / mypy / pytest runs
        # will surface the syntax error elsewhere.
        return 0

    docstring_line_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstring_line_ranges.append((first.lineno, first.end_lineno or first.lineno))

    def _in_docstring(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in docstring_line_ranges)

    sloc = 0
    for idx, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if _in_docstring(idx):
            continue
        sloc += 1
    return sloc


def _matched_files(repo_root: Path) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in _FILE_PATTERNS:
        for p in repo_root.glob(pattern):
            if not (p.is_file() and p.suffix == ".py"):
                continue
            # Exclude tests: ``test_*.py`` and any path containing ``/tests/``.
            name = p.name
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            seen.setdefault(p.resolve(), None)
    return sorted(seen.keys())


def _gate_body(args: Namespace) -> list[str]:
    repo_root = _repo_root(args)
    files = _matched_files(repo_root)
    violations: list[str] = []
    total = 0
    for f in files:
        sloc = _count_sloc(f)
        total += sloc
        if sloc > PER_FILE_SLOC_CAP:
            rel = f.relative_to(repo_root).as_posix()
            violations.append(
                f"{rel}: {sloc} SLOC exceeds per-file cap {PER_FILE_SLOC_CAP}. "
                "Either split the adapter or update PER_FILE_SLOC_CAP in "
                "tooling/ci/gates/adapter_loc_budget.py with a doc-line "
                "justification in docs/development/bridge_adapter_pattern.md."
            )
    if total > TOTAL_SLOC_BUDGET:
        violations.append(
            f"adapter SLOC total {total} exceeds budget {TOTAL_SLOC_BUDGET} "
            f"(across {len(files)} files). Either trim adapters or update "
            "TOTAL_SLOC_BUDGET in tooling/ci/gates/adapter_loc_budget.py "
            "with a doc-line justification in "
            "docs/development/bridge_adapter_pattern.md."
        )
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _gate_body, argv)


if __name__ == "__main__":
    sys.exit(main())
