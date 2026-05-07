"""CI gate: kernels may only reach into the bridge through the public seam.

K0 and K1 modules are allowed to import:

* ``bridge.client``
* ``bridge.contracts``
* ``bridge.testing``
* ``bridge._generated.<own_role>.*``  (k0 modules → ``bridge._generated.k0.*``;
  k1 modules → ``bridge._generated.k1.*``)
* ``bridge.ports``

Anything else (``bridge.core.*``, ``bridge.kernel.*``, ``bridge.sync.*``,
``bridge.connector.*``, ``bridge.codecs.*``, ``bridge.adapters.*``, the
private root ``bridge`` itself with attribute access into private modules)
is a wall violation.

A persistent allowlist file at ``tooling/ci/known_violations/bridge_imports.txt``
captures violations scheduled for remediation in a later milestone. Each
entry is ``<relpath>:<lineno>`` (the rest of the line is treated as a
comment). Allowlisted entries are excluded from the violation set.
"""

from __future__ import annotations

import ast
import sys
from argparse import Namespace
from pathlib import Path

from tooling.ci.gates._harness import run_gate

GATE_NAME = "bridge_not_imported_from_kernels"

_ALLOWED_PREFIXES: tuple[str, ...] = (
    "bridge.client",
    "bridge.contracts",
    "bridge.testing",
    "bridge.ports",
)

_FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "bridge.core",
    "bridge.kernel",
    "bridge.sync",
    "bridge.connector",
    "bridge.codecs",
    "bridge.adapters",
)

_ALLOWLIST_FILE_REL = Path("tooling") / "ci" / "known_violations" / "bridge_imports.txt"


def _repo_root(args: Namespace) -> Path:
    if args.repo_root:
        return Path(args.repo_root).resolve()
    return Path(__file__).resolve().parents[3]


def _load_allowlist(repo_root: Path) -> set[str]:
    f = repo_root / _ALLOWLIST_FILE_REL
    if not f.exists():
        return set()
    keys: set[str] = set()
    for line in f.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Format: "<relpath>:<lineno>  # optional comment"
        head = stripped.split("#", 1)[0].strip()
        if not head:
            continue
        # Normalise path separators so Windows-authored entries match.
        keys.add(head.replace("\\", "/"))
    return keys


def _allowed_for_role(name: str, role: str) -> bool:
    """Allow ``bridge._generated.<role>.*`` for the consuming kernel only."""
    own = f"bridge._generated.{role}"
    return name == own or name.startswith(own + ".")


def _is_forbidden_import(name: str, role: str) -> bool:
    if not name:
        return False
    if not (name == "bridge" or name.startswith("bridge.")):
        return False
    # Public seam — always OK.
    for allowed in _ALLOWED_PREFIXES:
        if name == allowed or name.startswith(allowed + "."):
            return False
    # Generated own-role tree — OK.
    if _allowed_for_role(name, role):
        return False
    # Generated foreign-role tree — forbidden.
    if name == "bridge._generated" or name.startswith("bridge._generated."):
        return True
    # Explicitly forbidden private subpackages.
    for forbidden in _FORBIDDEN_PREFIXES:
        if name == forbidden or name.startswith(forbidden + "."):
            return True
    # Bare ``import bridge`` (no submodule): forbidden — would let callers
    # reach into anything by attribute access.
    if name == "bridge":
        return True
    return False


def _iter_py_files(root: Path) -> list[Path]:
    skip_parts = {"__pycache__", "archived", "_generated", ".venv", "venv"}
    return sorted(p for p in root.rglob("*.py") if not any(part in skip_parts for part in p.parts))


def _scan_file(path: Path, repo_root: Path, role: str) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.relative_to(repo_root).as_posix()}: read error: {exc}"]
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        print(
            f"[bridge_not_imported_from_kernels] skipped (parse error): "
            f"{path.relative_to(repo_root).as_posix()}",
            file=sys.stderr,
        )
        return []
    rel = path.relative_to(repo_root).as_posix()
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden_import(alias.name, role):
                    out.append(f"{rel}:{node.lineno}  forbids {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            mod = node.module or ""
            if _is_forbidden_import(mod, role):
                out.append(f"{rel}:{node.lineno}  forbids {mod}")
    return out


def _body(args: Namespace) -> list[str]:
    root = _repo_root(args)
    allowlist = _load_allowlist(root)
    violations: list[str] = []
    for role in ("k0", "k1"):
        kernel_dir = root / role
        if not kernel_dir.exists():
            continue
        for py in _iter_py_files(kernel_dir):
            for line in _scan_file(py, root, role):
                key = line.split(" ", 1)[0]  # "<relpath>:<lineno>"
                if key in allowlist:
                    continue
                violations.append(line)
    return violations


def main(argv: list[str] | None = None) -> int:
    return run_gate(GATE_NAME, _body, argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
