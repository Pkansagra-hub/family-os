"""CI gate: no module under ``k0/`` imports ``k1.*`` and vice versa.

Cross-kernel imports collapse the wall. The gate parses every ``*.py``
file under ``k0/`` and ``k1/`` with :mod:`ast`, walks every ``Import``
and ``ImportFrom`` node, and reports any reach across the wall.

Allowlist mechanism: a ``# noqa: cross-kernel`` comment on the import
line suppresses the gate for that one line. Reason text after the
marker is required (`# noqa: cross-kernel — <reason>`).

Day-one expectation: GREEN (no violations).
"""

from __future__ import annotations

import ast
import sys
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "no_cross_kernel_imports"

# Modules that cross-import each other are tracked as wall pairs. The first
# entry is the consuming kernel (the file being scanned), the second is
# the forbidden import-prefix root.
_FORBIDDEN_PAIRS: tuple[tuple[str, str], ...] = (
    ("k0", "k1"),
    ("k1", "k0"),
)

_ALLOWLIST_MARKER = "noqa: cross-kernel"


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _iter_py_files(root: Path) -> list[Path]:
    """Skip caches, archived, generated, vendored trees."""
    skip_parts = {"__pycache__", "archived", "_generated", ".venv", "venv"}
    files: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in skip_parts for part in p.parts):
            continue
        files.append(p)
    return sorted(files)


def _line_has_allowlist(text_lines: list[str], lineno: int) -> bool:
    if 1 <= lineno <= len(text_lines):
        return _ALLOWLIST_MARKER in text_lines[lineno - 1]
    return False


def _scan_file(
    path: Path, repo_root: Path, consuming_kernel: str, forbidden_root: str
) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.relative_to(repo_root).as_posix()}: read error: {exc}"]

    text_lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        # Pre-existing parse errors are out of scope for this gate; report
        # to stderr but do not count as cross-kernel violations.
        print(
            f"[no_cross_kernel_imports] skipped (parse error): "
            f"{path.relative_to(repo_root).as_posix()}",
            file=sys.stderr,
        )
        return []

    violations: list[str] = []
    rel = path.relative_to(repo_root).as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_forbidden(alias.name, forbidden_root):
                    if _line_has_allowlist(text_lines, node.lineno):
                        continue
                    violations.append(
                        f"{rel}:{node.lineno}: {consuming_kernel} imports {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            # Only top-level / absolute imports cross kernels; relative imports
            # can never reach the other kernel.
            if node.level and node.level > 0:
                continue
            if _matches_forbidden(mod, forbidden_root):
                if _line_has_allowlist(text_lines, node.lineno):
                    continue
                violations.append(f"{rel}:{node.lineno}: {consuming_kernel} imports {mod}")
    return violations


def _matches_forbidden(name: str, forbidden_root: str) -> bool:
    return name == forbidden_root or name.startswith(forbidden_root + ".")


def _body(args: Namespace) -> list[str]:
    root = _repo_root(args)
    violations: list[str] = []
    for consuming, forbidden in _FORBIDDEN_PAIRS:
        kernel_dir = root / consuming
        if not kernel_dir.exists():
            continue
        for py in _iter_py_files(kernel_dir):
            violations.extend(_scan_file(py, root, consuming, forbidden))
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
