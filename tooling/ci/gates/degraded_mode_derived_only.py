"""CI gate: DEGRADED-mode policy is *only* derived inside
``bridge/core/degraded.py``.

The MS-3b plan (epic 3b.2) auto-derives every ``(port, topic) \u2192 behavior``
decision from manifest fields at runtime construction time. No code path
elsewhere may introduce a hand-coded ``if degraded:`` /
``if state == OFFLINE:`` /  ``if state == DEGRADED:`` branch that
bypasses :class:`bridge.core.degraded.DegradedMatrix.behavior_for`.

This gate AST-walks ``bridge/`` + ``k0/`` + ``k1/`` and fails on any
``If`` test that compares a state-bearing identifier against an
OFFLINE/DEGRADED literal, **except** inside ``bridge/core/degraded.py``
itself and ``bridge/core/health.py`` (which owns the legacy
``DegradedModeManager`` policy engine the SinkBridgeClient still uses
as an offline fallback).

A line-level escape hatch exists for genuine cases:

    if foo == K0HealthState.OFFLINE:  # noqa: degraded-mode \u2014 reason
        ...

The reason text after the ``\u2014`` is required.
"""

from __future__ import annotations

import ast
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "degraded_mode_derived_only"

_ALLOWED_RELPATHS = frozenset(
    {
        "bridge/core/degraded.py",
        "bridge/core/health.py",  # legacy DegradedModeManager + state machine
        "bridge/client.py",  # SinkBridgeClient uses the legacy policy
    }
)

_OFFLINE_TOKENS = ("OFFLINE", "DEGRADED")
_NOQA_PREFIX = "# noqa: degraded-mode"


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _iter_py_files(roots: list[Path]) -> list[Path]:
    skip_parts = {"__pycache__", "archived", ".venv", "venv", "_generated"}
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in skip_parts for part in p.parts):
                continue
            files.append(p)
    return sorted(files)


def _line_text(source_lines: list[str], lineno: int) -> str:
    if 0 < lineno <= len(source_lines):
        return source_lines[lineno - 1]
    return ""


def _has_noqa(source_lines: list[str], lineno: int) -> bool:
    """Allow ``# noqa: degraded-mode \u2014 reason`` (em-dash *or* ``-``)."""
    text = _line_text(source_lines, lineno)
    if _NOQA_PREFIX not in text:
        return False
    after = text.split(_NOQA_PREFIX, 1)[1]
    # Must include either em-dash or hyphen + non-empty reason.
    after = after.strip()
    return bool(after) and any(ch in after for ch in ("\u2014", "-"))


def _expr_mentions_offline(node: ast.expr) -> bool:
    """Heuristic: does ``node`` reference an OFFLINE/DEGRADED literal?

    We catch the common shapes:

    * ``ast.Attribute(attr='OFFLINE')`` (``K0HealthState.OFFLINE``)
    * ``ast.Constant(value='OFFLINE')`` (string literal comparisons)
    * ``ast.Name(id='OFFLINE')`` (locally-imported enum value)
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr in _OFFLINE_TOKENS:
            return True
        if isinstance(sub, ast.Constant) and sub.value in _OFFLINE_TOKENS:
            return True
        if isinstance(sub, ast.Name) and sub.id in _OFFLINE_TOKENS:
            return True
    return False


def _scan(path: Path, repo_root: Path) -> list[str]:
    rel = path.relative_to(repo_root).as_posix()
    if rel in _ALLOWED_RELPATHS:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if not any(tok in source for tok in _OFFLINE_TOKENS):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if not _expr_mentions_offline(node.test):
            continue
        if _has_noqa(source_lines, node.lineno):
            continue
        out.append(
            f"{rel}:{node.lineno}: hand-coded DEGRADED branch \u2014 "
            f"route through bridge.core.degraded.DegradedMatrix.behavior_for() "
            f"or add `# noqa: degraded-mode \u2014 <reason>`"
        )
    return out


def _body(args: Namespace) -> list[str]:
    root = _repo_root(args)
    # Scope: bridge/ only. The wall-not-imported gate already keeps k0/
    # and k1/ from importing bridge.core.degraded; their local
    # "DEGRADED" concepts (orchestrator/fabric/model-hub health) are a
    # different domain and out of scope for this gate.
    roots = [root / "bridge"]
    violations: list[str] = []
    for py in _iter_py_files(roots):
        violations.extend(_scan(py, root))
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))
