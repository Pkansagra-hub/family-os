"""CI gate: ``HttpBridgeClient`` is constructed only by ``BridgeRuntime``.

The MS-3a real-HTTP bridge client is a per-kernel namespace bag of
contract-bound publishers (``client.memory_write_v1.publish(...)`` and
successors). The plan-of-record requires that callers never instantiate
``HttpBridgeClient`` directly — they reach into the runtime's
``client`` slot, which is populated by
:meth:`bridge.runtime.BridgeRuntime.from_registry`.

This gate AST-walks every ``*.py`` under ``bridge/``, ``k0/``, and
``k1/`` (excluding the two files where construction is *legitimately*
defined: ``bridge/client.py`` and ``bridge/runtime.py``) and fails on
any direct ``HttpBridgeClient(...)`` call expression.

The runtime also enforces this with a private sentinel token, so a
direct call would raise ``RuntimeError`` at instantiation. The gate
exists as belt-and-braces defence in depth (per
``docs/architecture/whiteboard_k1/bridge_implementation_plan.md`` §3a.1
global rule on dual enforcement).
"""

from __future__ import annotations

import ast
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "bridge_client_construction_via_runtime_only"

_FORBIDDEN_NAME = "HttpBridgeClient"

# Files where ``HttpBridgeClient(...)`` may legitimately appear.
_ALLOWED_RELPATHS = frozenset(
    {
        "bridge/client.py",
        "bridge/runtime.py",
    }
)


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _iter_py_files(roots: list[Path]) -> list[Path]:
    skip_parts = {"__pycache__", "archived", ".venv", "venv"}
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in skip_parts for part in p.parts):
                continue
            files.append(p)
    return sorted(files)


def _name_of_call(func: ast.expr) -> str | None:
    """Return the textual name of a call's func, or None if unrecognised."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _scan(path: Path, repo_root: Path) -> list[str]:
    rel = path.relative_to(repo_root).as_posix()
    if rel in _ALLOWED_RELPATHS:
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []
    if _FORBIDDEN_NAME not in source:
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _name_of_call(node.func) == _FORBIDDEN_NAME:
            out.append(
                f"{rel}:{node.lineno}: direct construction of {_FORBIDDEN_NAME} "
                f"is forbidden — use BridgeRuntime.from_registry() instead"
            )
    return out


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
    import sys

    sys.exit(main(sys.argv[1:]))
