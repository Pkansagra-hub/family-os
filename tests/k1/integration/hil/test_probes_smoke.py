"""E8.M2.7 -- subprocess smoke test for all 8 kernel probes.

Each probe boots the real kernel and runs read-only assertions plus, for
some phases, a few real round-trips.  This test verifies every probe:

  * imports cleanly,
  * boots ``KernelService`` without crashing,
  * runs to completion within a generous timeout,
  * exits with a probe return code (``0`` = all green, ``1`` = some
    probe FAIL surfaced).  An exit code of ``2+`` indicates an
    unhandled exception or import error -- those are the regressions
    this test exists to catch.

Phases 3 and 5 surface pre-existing capability-execute timeouts in
their DAG/Saga harnesses unrelated to HIL; they are allowed to exit
with code ``1``.

The test is intentionally subprocess-based: probes call
``asyncio.run`` at module top level and would interfere with pytest's
event loop if imported in-process.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# tests/k1/integration/hil/test_probes_smoke.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]

PROBES: list[tuple[int, str]] = [
    (1, "scripts/kernel_probe_phase1.py"),
    (2, "scripts/kernel_probe_phase2_hil.py"),
    (3, "scripts/kernel_probe_phase3_fabric.py"),
    (4, "scripts/kernel_probe_phase4_planner.py"),
    (5, "scripts/kernel_probe_phase5_orchestrator.py"),
    (6, "scripts/kernel_probe_phase6_sessionstate.py"),
    (7, "scripts/kernel_probe_phase7_bus.py"),
    (8, "scripts/kernel_probe_phase8_modelhub.py"),
]

# Phases known to surface unrelated FAILs in their probe output (not HIL):
#   * phase 3 / 5 -- pre-existing capability-execute timeouts in
#     DAG/Saga harnesses,
#   * phase 4 -- planner SKETCH stage hits a stub-LLM JSON-parse
#     limitation when run with model_mode='test'.
# These may exit with code 1 (probe-detected issue), but must never exit
# with code >= 2 (uncaught exception / import error).
ALLOW_NONZERO: frozenset[int] = frozenset({3, 4, 5})

PROBE_TIMEOUT_S = 180


@pytest.mark.parametrize("phase,script", PROBES, ids=[f"phase{p}" for p, _ in PROBES])
def test_probe_runs_without_crashing(phase: int, script: str) -> None:
    """Boot the kernel via each probe and assert it doesn't crash."""

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    script_path = REPO_ROOT / script
    assert script_path.exists(), f"probe script missing: {script_path}"

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S,
    )

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    assert "Boot:" in combined, (
        f"phase {phase} ({script}) appears not to have booted the kernel.\n"
        f"--- stdout ---\n{result.stdout[-2000:]}\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )

    if phase in ALLOW_NONZERO:
        assert result.returncode in (0, 1), (
            f"phase {phase} ({script}) exited with code "
            f"{result.returncode} (expected 0 or 1).\n"
            f"--- stdout ---\n{result.stdout[-2000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )
    else:
        assert result.returncode == 0, (
            f"phase {phase} ({script}) exited with code {result.returncode} "
            f"(expected 0 -- probe surfaced a real regression).\n"
            f"--- stdout ---\n{result.stdout[-2000:]}\n"
            f"--- stderr ---\n{result.stderr[-2000:]}"
        )
