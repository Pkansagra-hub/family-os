"""Tests for the ``bridge_client_construction_via_runtime_only`` CI gate."""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

GATE = "tooling.ci.gates.bridge_client_construction_via_runtime_only"


def _make_repo(root: Path) -> Path:
    (root / "k0").mkdir()
    (root / "k0" / "__init__.py").write_text("", encoding="utf-8")
    (root / "k1").mkdir()
    (root / "k1" / "__init__.py").write_text("", encoding="utf-8")
    (root / "bridge").mkdir()
    (root / "bridge" / "__init__.py").write_text("", encoding="utf-8")
    return root


def _run(repo_root: Path) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", GATE, "--repo-root", str(repo_root)]
    real_repo = Path(__file__).resolve().parents[4]
    return subprocess.run(
        cmd,
        cwd=str(real_repo),
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_clean_repo_passes(tmp_path: Path) -> None:
    """A repo with no HttpBridgeClient construction sites: exit 0."""
    _make_repo(tmp_path)
    result = _run(tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "OK" in result.stderr


def test_gate_flags_direct_construction_in_k1(tmp_path: Path) -> None:
    """Direct ``HttpBridgeClient(...)`` in k1 code is rejected."""
    _make_repo(tmp_path)
    (tmp_path / "k1" / "rogue.py").write_text(
        textwrap.dedent("""
            from bridge.client import HttpBridgeClient

            def boot():
                # Forbidden: bypasses BridgeRuntime.from_registry().
                return HttpBridgeClient(_runtime_token=object())
            """).strip(),
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 1, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "k1/rogue.py" in result.stdout
    assert "HttpBridgeClient" in result.stdout


def test_gate_allows_construction_in_runtime_module(tmp_path: Path) -> None:
    """The two allowlisted files (bridge/client.py, bridge/runtime.py) may
    construct the class — the gate must skip them."""
    _make_repo(tmp_path)
    (tmp_path / "bridge" / "runtime.py").write_text(
        textwrap.dedent("""
            from bridge.client import HttpBridgeClient, _RUNTIME_CONSTRUCTION_TOKEN

            def make():
                return HttpBridgeClient(_runtime_token=_RUNTIME_CONSTRUCTION_TOKEN)
            """).strip(),
        encoding="utf-8",
    )
    (tmp_path / "bridge" / "client.py").write_text(
        textwrap.dedent("""
            class HttpBridgeClient:
                def __init__(self, *, _runtime_token):
                    pass

            def factory():
                return HttpBridgeClient(_runtime_token=object())
            """).strip(),
        encoding="utf-8",
    )
    result = _run(tmp_path)
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


def test_gate_warn_only_mode_returns_zero_with_violations(tmp_path: Path) -> None:
    """``--warn-only`` reports but does not fail."""
    _make_repo(tmp_path)
    (tmp_path / "k0" / "rogue.py").write_text(
        "from bridge.client import HttpBridgeClient\n"
        "x = HttpBridgeClient(_runtime_token=None)\n",
        encoding="utf-8",
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
    result = subprocess.run(cmd, cwd=str(real_repo), capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "k0/rogue.py" in result.stdout
    assert "WARN" in result.stderr
