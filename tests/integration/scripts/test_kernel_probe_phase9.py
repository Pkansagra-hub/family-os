"""M5.E4.I2 acceptance — smoke test for the phase-9 probe.

Runs ``scripts/kernel_probe_phase9_selfmodel.py`` as a subprocess
(stub mode), then asserts:

* Exit code 0.
* JSON report has the expected layered shape.
* Every check the plan calls out (M5.E4.I2 inspections #1..#9) is
  present in the report.
* No probe finished with status ``FAIL``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_MODULE = "scripts.kernel_probe_phase9_selfmodel"


def _run_probe(tmp_path: Path) -> dict:
    json_out = tmp_path / "phase9.json"
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            PROBE_MODULE,
            "--json",
            str(json_out),
            "--ssm-db",
            str(tmp_path / "ssm.db"),
            "--bridge-db",
            str(tmp_path / "bridge.db"),
            "--workflows-db",
            str(tmp_path / "workflows.db"),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"probe exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert json_out.exists(), "probe did not write JSON report"
    return json.loads(json_out.read_text(encoding="utf-8"))


def test_phase9_probe_exits_zero(tmp_path) -> None:
    report = _run_probe(tmp_path)
    counts = report["counts"]
    # No FAILs anywhere.
    assert counts["FAIL"] == 0, f"probe reported FAILs: {report}"
    # At least the bundle wiring + 13 situations should produce >= 30 OKs.
    assert counts["OK"] >= 30


def test_phase9_probe_layers_present(tmp_path) -> None:
    report = _run_probe(tmp_path)
    layers = {p["layer"] for p in report["probes"]}
    expected = {
        "Bundle wiring",  # I2 #1
        "Bus topics",  # I2 #2
        "Constitution",  # I2 #3
        "Identity",  # I2 #4
        "Composer",  # I2 #5
        "Policy evaluator",  # I2 #6
        "Session P3.5",  # I2 #7 (dispatcher gate) + #8 (capsule renderer)
        "E2E gate cycle",  # I3
        "HITL escalation",  # I4
        "V0 situations (S1..S13)",  # I5
        "Temporal drift",  # post-I5: state mutation between compose & evaluate
    }
    missing = expected - layers
    assert not missing, f"phase-9 probe missing layers: {missing}"


def test_phase9_probe_covers_13_situations(tmp_path) -> None:
    report = _run_probe(tmp_path)
    sit_probes = [p for p in report["probes"] if p["layer"] == "V0 situations (S1..S13)"]
    # 13 situation checks + the "13/13 covered" summary = 14 entries.
    assert len(sit_probes) == 14, sit_probes
    summary = next(p for p in sit_probes if p["name"] == "13/13 covered")
    assert summary["status"] == "OK", summary


def test_phase9_bundle_health_ok(tmp_path) -> None:
    report = _run_probe(tmp_path)
    health_status = next(
        p
        for p in report["probes"]
        if p["layer"] == "Bundle wiring" and p["name"] == "health.status"
    )
    assert health_status["status"] == "OK"
    assert health_status["value"] == "ok"


def test_phase9_temporal_drift_layer(tmp_path) -> None:
    """Probe must surface T0→T2 mutation behaviour for all four drift kinds."""
    report = _run_probe(tmp_path)
    drift = [p for p in report["probes"] if p["layer"] == "Temporal drift"]
    names = {p["name"] for p in drift}
    # The four drift kinds the user critique called out.
    required = {
        "T2 constitution mutation observed",  # constitution drift
        "session-B sees new role",  # cross-session interference
        "tier=1 (escalated) \u2192 ALLOW",  # identity escalation
        "HIGH \u00d7 stale",  # freshness decay matrix
    }
    missing = required - names
    assert not missing, f"temporal-drift probe missing checks: {missing}"
    # No FAILs in the drift layer (INFO is allowed for documented gaps).
    fails = [p for p in drift if p["status"] == "FAIL"]
    assert not fails, f"temporal-drift FAILs: {fails}"
