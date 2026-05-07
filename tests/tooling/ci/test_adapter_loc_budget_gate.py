"""Contract tests for ``tooling/ci/gates/adapter_loc_budget.py`` (MS-4).

We don't pin the gate's exact violation list to current state (that would
be brittle across future genuine adapter additions). Instead we lock the
gate's *behaviour*:

* Counts SLOC excluding blank lines, comments, and module/class docstrings.
* Excludes test files (``test_*.py`` / ``*_test.py``).
* Reports per-file violations when a file exceeds ``PER_FILE_SLOC_CAP``.
* Reports a total-budget violation when sum exceeds ``TOTAL_SLOC_BUDGET``.
* Returns 0 on a clean fixture and 1 on a budget breach.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tooling.ci.gates.adapter_loc_budget import (
    PER_FILE_SLOC_CAP,
    TOTAL_SLOC_BUDGET,
    _count_sloc,
    _matched_files,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")


def test_count_sloc_excludes_blank_and_comment_lines(tmp_path: Path) -> None:
    f = tmp_path / "sample.py"
    _write(
        f,
        '''\
        """Module docstring.

        Spans multiple lines and is excluded.
        """

        # leading comment is excluded
        from __future__ import annotations

        import os  # trailing comment counts the line
        ''',
    )
    # "from __future__ import annotations" + "import os  # ..."
    assert _count_sloc(f) == 2


def test_count_sloc_excludes_class_docstring(tmp_path: Path) -> None:
    f = tmp_path / "with_class.py"
    _write(
        f,
        '''\
        class A:
            """Class doc.

            Multi-line.
            """
            x = 1
            y = 2
        ''',
    )
    # "class A:", "x = 1", "y = 2" → 3
    assert _count_sloc(f) == 3


def test_count_sloc_keeps_function_docstrings(tmp_path: Path) -> None:
    """Function docstrings are intentionally counted (single-line, hard to abuse)."""
    f = tmp_path / "with_fn.py"
    _write(
        f,
        '''\
        def f():
            """Single-line doc."""
            return 1
        ''',
    )
    # def f():, "...", return 1 → 3
    assert _count_sloc(f) == 3


def test_matched_files_excludes_tests(tmp_path: Path) -> None:
    """``test_*.py`` and ``*_test.py`` are skipped even if they match a glob."""
    repo = tmp_path / "repo"
    (repo / "k1" / "fabric" / "adapters").mkdir(parents=True)
    (repo / "k1" / "fabric" / "adapters" / "bridge_x.py").write_text("x = 1\n")
    (repo / "k1" / "fabric" / "adapters" / "test_bridge.py").write_text("x = 1\n")
    (repo / "k1" / "fabric" / "adapters" / "bridge_test.py").write_text("x = 1\n")
    matched = {p.name for p in _matched_files(repo)}
    assert matched == {"bridge_x.py"}


def _run_gate(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tooling.ci.gates.adapter_loc_budget",
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[3],
    )


def test_gate_passes_on_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "k1").mkdir(parents=True)
    result = _run_gate(repo)
    assert result.returncode == 0, result.stdout + result.stderr


def test_gate_fails_when_per_file_cap_exceeded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    target = repo / "k1" / "modX" / "adapters" / "bridge_huge.py"
    target.parent.mkdir(parents=True)
    body = "x = 1\n" * (PER_FILE_SLOC_CAP + 5)
    target.write_text(body, encoding="utf-8")
    result = _run_gate(repo)
    assert result.returncode == 1
    assert "exceeds per-file cap" in result.stdout
    assert "bridge_huge.py" in result.stdout


def test_gate_fails_when_total_budget_exceeded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    adapters = repo / "k1" / "modY" / "adapters"
    adapters.mkdir(parents=True)
    # 6 files each just under the per-file cap; together they exceed total.
    per = PER_FILE_SLOC_CAP - 1
    n_files = (TOTAL_SLOC_BUDGET // per) + 2
    for i in range(n_files):
        (adapters / f"bridge_{i}.py").write_text("x = 1\n" * per, encoding="utf-8")
    result = _run_gate(repo)
    assert result.returncode == 1
    assert "exceeds budget" in result.stdout


def test_gate_passes_on_real_workspace() -> None:
    """The actual K1 adapter tree must satisfy the budget at HEAD."""
    repo_root = Path(__file__).resolve().parents[3]
    result = _run_gate(repo_root)
    assert result.returncode == 0, (
        f"adapter_loc_budget regressed at HEAD\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
