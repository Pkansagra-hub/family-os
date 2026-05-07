"""MS-2.5 Epic 2.5.3 — IBridgePort rename completeness.

Asserts that no module under ``k1/`` defines a class named ``IBridgePort``
at module level. The 3 historical definitions have been renamed to
``IBridgeRuntime`` / ``IFabricK0Port`` / ``IPlannerWritePort``.

This is the D6 single-ibridge-port-definition gate.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_no_ibridgeport_class_definitions_in_repo() -> None:
    pattern = re.compile(r"^class IBridgePort\b")
    offenders: list[str] = []
    for py in REPO_ROOT.rglob("*.py"):
        # Skip vendored / cache dirs.
        parts = set(py.parts)
        if parts & {".venv", "venv", "__pycache__", "node_modules"}:
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line in text.splitlines():
            if pattern.match(line):
                offenders.append(py.relative_to(REPO_ROOT).as_posix())
                break
    assert offenders == [], "Found stray `class IBridgePort` definitions: " + ", ".join(offenders)


def test_renamed_classes_are_importable() -> None:
    from k1.fabric.ports.bridge_port import IFabricK0Port
    from k1.kernel.ports.bridge_port import IBridgeRuntime
    from k1.planner.ports.bridge_port import IPlannerWritePort

    assert IBridgeRuntime is not None
    assert IFabricK0Port is not None
    assert IPlannerWritePort is not None
