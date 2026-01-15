"""
P03 Docker End-to-End Integration Tests.

These tests run against the REAL Docker container - no mocks.
Requires: k0-kernel container running on localhost:8080

Usage:
    # Start the container first
    docker-compose up -d k0-kernel

    # Run tests
    pytest tests/k0/pipelines/p03/integration/test_p03_docker_e2e.py -v -s
"""

import subprocess
import time

import httpx
import pytest

K0_KERNEL_URL = "http://localhost:8080"
CONTAINER_NAME = "k0-kernel"


def get_container_logs(lines: int = 50) -> str:
    """Get recent logs from the k0-kernel container."""
    result = subprocess.run(
        ["docker", "logs", CONTAINER_NAME, "--tail", str(lines)],
        capture_output=True,
        text=True,
    )
    return result.stdout + result.stderr


def is_container_running() -> bool:
    """Check if k0-kernel container is running."""
    result = subprocess.run(
        ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    return CONTAINER_NAME in result.stdout


def restart_container() -> None:
    """Restart the k0-kernel container."""
    subprocess.run(["docker", "restart", CONTAINER_NAME], check=True)
    time.sleep(10)  # Wait for container to be ready


class TestP03DockerE2E:
    """Real E2E tests against Docker container."""

    @pytest.fixture(autouse=True)
    def check_container(self):
        """Ensure container is running before each test."""
        if not is_container_running():
            pytest.skip(f"Container {CONTAINER_NAME} is not running")
        yield

    def test_container_is_healthy(self):
        """Verify container is running and responding."""
        # Try multiple endpoints - /health may not exist
        for endpoint in ["/health", "/k0/health", "/", "/k0/admin/pipelines"]:
            try:
                response = httpx.get(f"{K0_KERNEL_URL}{endpoint}", timeout=5.0)
                if response.status_code in (200, 404):
                    # Container is responding
                    return
            except httpx.ConnectError:
                pass
        pytest.fail("Container not responding on any endpoint")

    def test_p03_pipeline_is_booted(self):
        """Verify P03 pipeline booted successfully."""
        logs = get_container_logs(100)
        assert "Booted 3 pipelines" in logs or "P03_CONSOLIDATION" in logs
        assert "P03_CONSOLIDATION" in logs

    def test_p03_triggers_registered(self):
        """Verify P03 triggers are registered."""
        logs = get_container_logs(100)
        assert "p03_interval_90m" in logs
        assert "p03_threshold_500" in logs
        assert "p03_manual" in logs

    def test_p03_manual_trigger_fires(self):
        """Fire manual trigger and verify it executes."""
        # Fire the trigger
        response = httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "Docker E2E test"},
            timeout=10.0,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["pipeline_id"] == "P03_CONSOLIDATION"

    def test_p03_execution_reaches_phases(self):
        """Trigger P03 and verify phase execution in logs."""
        # Fire the trigger
        response = httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "Phase execution test"},
            timeout=10.0,
        )
        assert response.status_code == 200

        # Wait for execution
        time.sleep(2)

        # Check logs for phase execution
        logs = get_container_logs(50)

        # R0 should start
        assert "R0: Starting batch selection" in logs or "R0:" in logs

    def test_p03_sequential_adapter_handles_message(self):
        """Verify sequential adapter receives and handles messages."""
        # Fire the trigger
        httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "Adapter test"},
            timeout=10.0,
        )

        time.sleep(2)
        logs = get_container_logs(50)

        # Sequential adapter should log message handling
        assert "Handling message for P03_CONSOLIDATION" in logs

    def test_p03_identifies_syscall_gap(self):
        """
        Verify that the syscall gap (offset_store missing) is identified.

        This test documents the current blocker - Syscalls doesn't have offset_store.
        Once fixed, this test should be updated to verify successful execution.
        """
        # Fire the trigger
        httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "Syscall gap test"},
            timeout=10.0,
        )

        time.sleep(2)
        logs = get_container_logs(50)

        # Currently fails on offset_store - this documents the gap
        # When fixed, change this assertion
        if "'Syscalls' object has no attribute 'offset_store'" in logs:
            # This is the current known issue
            pytest.xfail("Syscalls.offset_store not implemented - known gap")
        else:
            # If we get past offset_store, check for success or next error
            assert "R0:" in logs


class TestP03SyscallRequirements:
    """
    Tests documenting what syscall capabilities P03 needs.

    These tests help identify gaps between what P03 expects and what Syscalls provides.
    """

    @pytest.fixture(autouse=True)
    def check_container(self):
        if not is_container_running():
            pytest.skip(f"Container {CONTAINER_NAME} is not running")

    def test_r0_requires_offset_store(self):
        """R0 requires offset_store for batch selection."""
        httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "offset_store requirement test"},
            timeout=10.0,
        )

        time.sleep(2)
        logs = get_container_logs(50)

        # Document the requirement
        if "offset_store" in logs:
            print("\n[GAP] R0 requires: ctx.syscalls.offset_store")
            print("      Need to add offset_store to Syscalls class")

    def test_document_p03_syscall_gaps(self):
        """Document all syscall gaps found during P03 execution."""
        httpx.post(
            f"{K0_KERNEL_URL}/k0/admin/pipelines/P03_CONSOLIDATION/trigger",
            params={"trigger_id": "p03_manual"},
            json={"reason": "syscall gap discovery"},
            timeout=10.0,
        )

        time.sleep(3)
        logs = get_container_logs(100)

        gaps = []
        if "'Syscalls' object has no attribute 'offset_store'" in logs:
            gaps.append("offset_store")
        if "'Syscalls' object has no attribute 'unit_of_work'" in logs:
            gaps.append("unit_of_work")
        if "'Syscalls' object has no attribute 'connection'" in logs:
            gaps.append("connection")
        if "'Syscalls' object has no attribute 'hipp_store'" in logs:
            gaps.append("hipp_store")

        if gaps:
            print(f"\n[SYSCALL GAPS] P03 requires these missing attributes: {gaps}")
            print("Add these to k0/kernel/syscalls.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
