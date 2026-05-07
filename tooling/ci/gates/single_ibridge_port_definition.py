"""CI gate: ``IBridgePort`` (the legacy umbrella name) exists nowhere.

The MS-2.5 rename split the umbrella ``IBridgePort`` into role-specific
ports: ``IBridgeRuntime``, ``IFabricK0Port``, ``IPlannerWritePort``, and
the existing ``IKernel*Port`` family. The old name MUST NOT reappear —
re-introducing it would re-create the umbrella the rename eliminated.

The gate scans every ``*.py`` under ``bridge/``, ``k0/``, ``k1/`` for
``class IBridgePort`` definitions or ``IBridgePort`` identifiers used in
class-bases (caught lexically; ``ast.parse`` confirms the line is a
class definition).
"""

from __future__ import annotations

import ast
import re
import sys
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "single_ibridge_port_definition"

_FORBIDDEN_NAME = "IBridgePort"
_CLASS_DEF_REGEX = re.compile(r"^class\s+IBridgePort\b")


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _iter_py_files(roots: list[Path]) -> list[Path]:
    skip_parts = {"__pycache__", "archived", "_generated", ".venv", "venv"}
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in skip_parts for part in p.parts):
                continue
            files.append(p)
    return sorted(files)


def _scan(path: Path, repo_root: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rel = path.relative_to(repo_root).as_posix()

    # Cheap pre-filter so we only AST-parse files containing the literal name.
    if _FORBIDDEN_NAME not in source:
        return []

    out: list[str] = []
    # Lexical class definition.
    for lineno, line in enumerate(source.splitlines(), start=1):
        if _CLASS_DEF_REGEX.match(line.lstrip()):
            out.append(f"{rel}:{lineno}: defines class {_FORBIDDEN_NAME}")

    # AST class-base check: ``class X(IBridgePort):``.
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = _name_of(base)
                if base_name == _FORBIDDEN_NAME:
                    out.append(
                        f"{rel}:{node.lineno}: class {node.name} subclasses " f"{_FORBIDDEN_NAME}"
                    )
    return out


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _body(args: Namespace) -> list[str]:
    root = _repo_root(args)
    roots = [root / "bridge", root / "k0", root / "k1"]
    violations: list[str] = []
    for py in _iter_py_files(roots):
        violations.extend(_scan(py, root))
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
