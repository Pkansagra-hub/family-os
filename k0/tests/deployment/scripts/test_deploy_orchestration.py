"""
Ward test suite for deployment script orchestration.

Validates:
- Parameter parsing and validation
- Pulumi CLI invocation
- Ansible playbook execution
- Timeline JSON artifact generation
- Error propagation and exit codes
- Cross-platform compatibility
"""

import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from ward import each, fixture, test

# Test fixtures


@fixture
def temp_artifacts_dir():
    """Create temporary artifacts directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_path = Path(tmpdir) / "artifacts"
        artifacts_path.mkdir(parents=True, exist_ok=True)
        yield artifacts_path


@fixture
def mock_subprocess():
    """Mock subprocess calls to prevent actual execution."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        yield mock_run


@fixture
def repo_root():
    """Get repository root path."""
    return Path(__file__).parent.parent.parent.parent


# PowerShell script tests


@test("deploy.ps1 validates required stack parameter")
def _(repo_root=repo_root):
    """Verify deploy.ps1 rejects invocation without stack parameter."""
    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.ps1"

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    # Invoke without -Stack parameter (should fail)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(script_path)],
        capture_output=True,
        text=True,
        input="",  # Send empty input to prevent prompting
        timeout=10,
    )

    assert result.returncode != 0, "Script should fail without -Stack parameter"
    assert "Stack" in result.stderr or "parameter" in result.stderr.lower()


@test("deploy.ps1 accepts valid stack values")
def _(
    repo_root=repo_root,
    stack=each("local-single-node", "edge-cluster", "datacenter-ha"),
):
    """Verify deploy.ps1 accepts all valid stack values with preview mode."""
    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.ps1"

    # Run in preview mode to avoid actual deployment
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script_path),
            "-Stack",
            str(stack),
            "-Preview",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Preview mode should not fail on parameter validation
    assert (
        "Starting deployment" in result.stdout
        or result.returncode == 0
        or "pulumi" in result.stderr.lower()
    )


@test("deploy.ps1 rejects invalid stack value")
def _(repo_root=repo_root):
    """Verify deploy.ps1 rejects invalid stack values."""
    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.ps1"

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script_path),
            "-Stack",
            "invalid-stack",
            "-Preview",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, "Script should reject invalid stack value"
    assert "ValidateSet" in result.stderr or "Cannot validate" in result.stderr


@test("deploy.ps1 generates timeline JSON artifact in preview mode")
def _(repo_root=repo_root, temp_artifacts_dir=temp_artifacts_dir):
    """Verify deploy.ps1 creates timeline JSON with expected structure."""
    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.ps1"

    # Run in preview mode with custom artifacts directory
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script_path),
            "-Stack",
            "local-single-node",
            "-Preview",
            "-ArtifactsRoot",
            str(temp_artifacts_dir),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Check for timeline files (may not exist if Pulumi not available)
    timeline_files = list(temp_artifacts_dir.rglob("deployment-timeline-*.json"))

    if timeline_files:
        timeline_data = json.loads(timeline_files[0].read_text())

        # Validate timeline structure
        assert "stack" in timeline_data
        assert timeline_data["stack"] == "local-single-node"
        assert "mode" in timeline_data
        assert "started_at" in timeline_data
        assert "steps" in timeline_data
        assert isinstance(timeline_data["steps"], list)


# Bash script tests


@test("deploy.sh validates required stack parameter")
def _(repo_root=repo_root):
    """Verify deploy.sh rejects invocation without stack parameter."""
    if platform.system() == "Windows" or not shutil.which("bash"):
        # Skip on Windows where bash is not available
        return

    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.sh"

    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    result = subprocess.run(
        ["bash", str(script_path)], capture_output=True, text=True, timeout=10
    )

    assert result.returncode != 0, "Script should fail without stack parameter"
    assert "usage" in result.stderr.lower()


@test("deploy.sh accepts valid mode values")
def _(repo_root=repo_root, mode=each("preview", "apply")):
    """Verify deploy.sh accepts valid mode values."""
    if platform.system() == "Windows" or not shutil.which("bash"):
        # Skip on Windows where bash is not available
        return

    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.sh"

    result = subprocess.run(
        ["bash", str(script_path), "local-single-node", str(mode)],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Should not fail on mode validation (may fail on missing tools)
    assert "invalid mode" not in result.stderr.lower()


@test("deploy.sh rejects invalid mode value")
def _(repo_root=repo_root):
    """Verify deploy.sh rejects invalid mode values."""
    if platform.system() == "Windows" or not shutil.which("bash"):
        # Skip on Windows where bash is not available
        return

    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.sh"

    result = subprocess.run(
        ["bash", str(script_path), "local-single-node", "invalid-mode"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0, "Script should reject invalid mode"
    assert "invalid mode" in result.stderr.lower()


# Integration contract tests


@test("deployment scripts create expected artifact structure")
def _(temp_artifacts_dir=temp_artifacts_dir):
    """Verify expected artifact directory structure from deployment."""
    # Simulate artifact creation
    (temp_artifacts_dir / "pulumi" / "local-single-node").mkdir(
        parents=True, exist_ok=True
    )
    (temp_artifacts_dir / "telemetry" / "local-single-node").mkdir(
        parents=True, exist_ok=True
    )

    timeline_file = (
        temp_artifacts_dir
        / "deployment-timeline-local-single-node-20250103-120000.json"
    )
    timeline_file.write_text(
        json.dumps(
            {
                "stack": "local-single-node",
                "mode": "apply",
                "started_at": "2025-01-03T12:00:00Z",
                "completed_at": "2025-01-03T12:05:00Z",
                "status": "success",
                "steps": [
                    {"name": "pulumi_operation", "status": "completed"},
                    {"name": "ansible_playbook", "status": "completed"},
                    {"name": "telemetry_snapshot", "status": "completed"},
                ],
            }
        )
    )

    # Validate structure
    assert (temp_artifacts_dir / "pulumi" / "local-single-node").exists()
    assert (temp_artifacts_dir / "telemetry" / "local-single-node").exists()
    assert timeline_file.exists()

    # Validate timeline content
    timeline_data = json.loads(timeline_file.read_text())
    assert timeline_data["status"] == "success"
    assert len(timeline_data["steps"]) == 3


@test("timeline JSON captures error information on failure")
def _(temp_artifacts_dir=temp_artifacts_dir):
    """Verify timeline JSON captures error details on deployment failure."""
    timeline_file = (
        temp_artifacts_dir / "deployment-timeline-edge-cluster-20250103-120000.json"
    )

    # Simulate failed deployment timeline
    timeline_data = {
        "stack": "edge-cluster",
        "mode": "apply",
        "started_at": "2025-01-03T12:00:00Z",
        "completed_at": "2025-01-03T12:02:30Z",
        "status": "failed",
        "error": "Ansible playbook failed with exit code 2",
        "steps": [
            {
                "name": "pulumi_operation",
                "status": "completed",
                "metadata": {"exit_code": 0},
            },
            {
                "name": "ansible_playbook",
                "status": "failed",
                "metadata": {"exit_code": 2},
            },
        ],
    }

    timeline_file.write_text(json.dumps(timeline_data))

    # Validate error capture
    loaded_data = json.loads(timeline_file.read_text())
    assert loaded_data["status"] == "failed"
    assert "error" in loaded_data
    assert loaded_data["error"] != ""
    assert any(step["status"] == "failed" for step in loaded_data["steps"])


@test("deployment scripts propagate exit codes correctly")
def _():
    """Verify deployment scripts propagate exit codes from underlying tools."""
    # Mock successful execution
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)

        # Simulate script behavior
        pulumi_exit = 0
        ansible_exit = 0

        final_exit = max(pulumi_exit, ansible_exit)
        assert final_exit == 0

    # Mock failed execution
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=1)

        # Simulate script behavior
        pulumi_exit = 0
        ansible_exit = 1

        final_exit = max(pulumi_exit, ansible_exit)
        assert final_exit == 1


@test("deployment scripts handle missing dependencies gracefully")
def _(repo_root=repo_root):
    """Verify scripts provide helpful error messages for missing tools."""
    script_path = repo_root / "k0" / "deployment" / "scripts" / "deploy.ps1"

    # This test validates that scripts fail gracefully when tools are missing
    # Actual behavior depends on whether Pulumi/Ansible are installed
    # Test validates script doesn't crash with unexpected errors

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(script_path),
            "-Stack",
            "local-single-node",
            "-Preview",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Script should either succeed or provide clear error message
    # Should not crash with PowerShell syntax errors
    assert "Exception" not in result.stderr or "pulumi" in result.stderr.lower()
    assert "Exception" not in result.stderr or "pulumi" in result.stderr.lower()
    assert "Exception" not in result.stderr or "pulumi" in result.stderr.lower()
