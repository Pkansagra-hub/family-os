"""Tests for the ``degraded_mode_derived_only`` CI gate."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

GATE = "tooling.ci.gates.degraded_mode_derived_only"


def _make_repo(root: Path) -> Path:
    (root / "bridge").mkdir()
    (root / "bridge" / "__init__.py").write_text("", encoding="utf-8")
    (root / "bridge" / "core").mkdir()
    (root / "bridge" / "core" / "__init__.py").write_text("", encoding="utf-8")
    return root


def _run(repo_root: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", GATE, "--repo-root", str(repo_root)]
    real_repo = Path(__file__).resolve().parents[4]
    return subprocess.run(cmd, cwd=str(real_repo), capture_output=True, text=True, check=False)


def test_gate_clean_repo_passes(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    res = _run(tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_gate_flags_hand_coded_offline_branch(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "rogue.py").write_text(
        textwrap.dedent("""
            from bridge.core.health import K0HealthState

            def go(state):
                if state == K0HealthState.OFFLINE:
                    return "queue"
                return "send"
            """).strip(),
        encoding="utf-8",
    )
    res = _run(tmp_path)
    assert res.returncode == 1
    assert "rogue.py" in res.stdout
    assert "DEGRADED branch" in res.stdout


def test_gate_allows_noqa_with_reason(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "explained.py").write_text(
        textwrap.dedent("""
            from bridge.core.health import K0HealthState

            def go(state):
                if state == K0HealthState.OFFLINE:  # noqa: degraded-mode \u2014 audit log only
                    return "log"
                return "ok"
            """).strip(),
        encoding="utf-8",
    )
    res = _run(tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr


def test_gate_skips_degraded_module_itself(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "core" / "degraded.py").write_text(
        textwrap.dedent("""
            from bridge.core.health import K0HealthState

            def behavior_for_state(state):
                if state == K0HealthState.OFFLINE:
                    return "raise"
                if state == K0HealthState.DEGRADED:
                    return "queue"
                return None
            """).strip(),
        encoding="utf-8",
    )
    res = _run(tmp_path)
    assert res.returncode == 0


def test_gate_skips_health_module(tmp_path: Path) -> None:
    """``bridge/core/health.py`` owns the legacy DegradedModeManager and may
    branch on state freely."""
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "core" / "health.py").write_text(
        textwrap.dedent("""
            class K0HealthState:
                OFFLINE = "OFFLINE"

            def go(state):
                if state == K0HealthState.OFFLINE:
                    return "x"
                return "y"
            """).strip(),
        encoding="utf-8",
    )
    res = _run(tmp_path)
    assert res.returncode == 0


def test_gate_warn_only_returns_zero_with_violation(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "rogue.py").write_text(
        "if state == 'OFFLINE':\n    pass\n", encoding="utf-8"
    )
    cmd = [
        sys.executable,
        "-m",
        GATE,
        "--repo-root",
        str(tmp_path),
        "--warn-only",
    ]
    real_repo = Path(__file__).resolve().parents[4]
    res = subprocess.run(cmd, cwd=str(real_repo), capture_output=True, text=True, check=False)
    assert res.returncode == 0
