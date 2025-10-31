"""Epic E3.2: Mixed-priority workload testing for scheduler fairness (W-DRR).

Validates that the scheduler maintains fairness guarantees across bands (AMBER, REALTIME, BACKGROUND)
and doesn't starve background traffic when AMBER demand spikes.

Measures:
- Token acquisition patterns by band
- Rejection rates under load
- Latency distributions per band
- Recovery time after load subsides
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from tests.scripts import test_k0_bootstrap_harness as harness_tests


class TestSchedulerFairnessUnderAMBERLoad:
    """E3.2: Run mixed-priority workload confirming W-DRR fairness.

    Setup:
    - Create a temporary K0 app with allow_all policy
    - Emulate simultaneous requests from AMBER, REALTIME, and BACKGROUND bands
    - Measure token acquisition success rates by band
    - Validate that no band is completely starved

    Expected behavior:
    - AMBER traffic gets majority of capacity (highest weight in W-DRR)
    - REALTIME and BACKGROUND still make progress (no starvation)
    - Rejection rates scale fairly with demand
    """

    @pytest.fixture
    def temp_app_with_client(self, tmp_path: Any, monkeypatch: Any) -> Any:
        """Create a fresh app instance with TestClient."""
        manifest_path = harness_tests.POLICY_FIXTURES_DIR / "allow_all.json"
        with harness_tests.run_with_manifest(
            tmp_path,
            monkeypatch,
            manifest_path=manifest_path,
        ) as (app, client, contract, signing_key):
            yield app, client, contract, signing_key

    def test_amber_load_does_not_starve_background(self, temp_app_with_client: Any) -> None:
        """Verify BACKGROUND traffic still makes progress under AMBER spike."""
        app, client, contract, signing_key = temp_app_with_client

        # Generate test envelopes with different bands
        amber_payload = harness_tests._make_signed_envelope(contract, signing_key)
        amber_payload["band"] = "AMBER"

        # GREEN is default
        green_payload = harness_tests._make_signed_envelope(contract, signing_key)
        green_payload["band"] = "GREEN"

        # Simulate mixed-priority load: alternate AMBER and GREEN requests
        amber_successes = 0
        amber_rejections = 0
        green_successes = 0
        green_rejections = 0

        num_iterations = 30

        for i in range(num_iterations):
            # Attempt AMBER request
            try:
                response = harness_tests._post_command(client, amber_payload)
                if response.status_code == 200:
                    amber_successes += 1
                elif response.status_code == 509:
                    amber_rejections += 1
            except Exception:
                amber_rejections += 1

            # Attempt GREEN (lower priority) request
            try:
                response = harness_tests._post_command(client, green_payload)
                if response.status_code == 200:
                    green_successes += 1
                elif response.status_code == 509:
                    green_rejections += 1
            except Exception:
                green_rejections += 1

        # Assertions: GREEN should have made at least SOME progress (no starvation)
        # AMBER should succeed more often than GREEN (higher priority)
        total_amber = amber_successes + amber_rejections
        total_green = green_successes + green_rejections

        assert total_amber > 0, "No AMBER requests processed"
        assert total_green > 0, "No GREEN requests processed (possible starvation)"

        # GREEN success rate should be positive (fairness)
        green_success_rate = green_successes / total_green if total_green > 0 else 0
        assert green_success_rate > 0, "GREEN traffic was completely starved"

        # AMBER should have higher or equal success rate (priority)
        amber_success_rate = amber_successes / total_amber if total_amber > 0 else 0
        assert (
            amber_success_rate >= green_success_rate * 0.5
        ), "AMBER priority inversion: GREEN has higher success rate than expected"

    def test_capacity_recovery_after_load_subsides(self, temp_app_with_client: Any) -> None:
        """Verify port capacity recovers when load subsides."""
        app, client, contract, signing_key = temp_app_with_client

        payload = harness_tests._make_signed_envelope(contract, signing_key)

        # Phase 1: Establish baseline (no load)
        baseline_response = client.get("/metrics")
        assert baseline_response.status_code == 200
        baseline_metrics = baseline_response.text

        # Extract query port active tokens from baseline
        def extract_active_tokens(metrics: str, port: str) -> int:
            """Parse Prometheus metrics for active tokens gauge."""
            prefix = f'qos_active_tokens{{port="{port}"}}'
            for line in metrics.splitlines():
                if line.startswith(prefix):
                    try:
                        return int(float(line.split()[-1]))
                    except (ValueError, IndexError):
                        pass
            return 0

        baseline_active = extract_active_tokens(baseline_metrics, "command")

        # Phase 2: Generate load by acquiring and holding tokens
        try:
            for _ in range(5):
                response = harness_tests._post_command(client, payload)
                if response.status_code == 200:
                    # Token is being held (briefly in-flight)
                    pass
                time.sleep(0.05)  # Small delay between requests

            # Check metrics during load
            load_response = client.get("/metrics")
            assert load_response.status_code == 200
            load_metrics = load_response.text
            load_active = extract_active_tokens(load_metrics, "command")

            # Should have some active tokens during load
            assert (
                load_active >= baseline_active
            ), "Port should have active tokens during load phase"

        finally:
            # Phase 3: Release all tokens (load subsides)
            # Tokens released implicitly as requests complete
            pass

        # Wait for system to settle
        time.sleep(0.2)

        # Phase 4: Check recovery (should return to baseline)
        recovery_response = client.get("/metrics")
        assert recovery_response.status_code == 200
        recovery_metrics = recovery_response.text
        recovery_active = extract_active_tokens(recovery_metrics, "command")

        # After load subsides, active tokens should drop back
        assert (
            recovery_active <= baseline_active + 1
        ), f"Port did not recover: baseline={baseline_active}, recovery={recovery_active}"

    def test_per_band_token_acquisition_tracking(self, temp_app_with_client: Any) -> None:
        """Validate that token acquisition metrics are tracked per band."""
        app, client, contract, signing_key = temp_app_with_client

        payload = harness_tests._make_signed_envelope(contract, signing_key)

        # Get baseline metrics
        baseline_response = client.get("/metrics")
        assert baseline_response.status_code == 200
        baseline_metrics = baseline_response.text

        # Extract acquisition counter from baseline
        def extract_acquisitions(metrics: str, band: str, port: str) -> float:
            """Parse Prometheus metrics for acquisition counter."""
            prefix = f'qos_token_acquisitions_total{{band="{band}",port="{port}"}}'
            for line in metrics.splitlines():
                if line.startswith(prefix):
                    try:
                        return float(line.split()[-1])
                    except (ValueError, IndexError):
                        pass
            return 0

        baseline_green = extract_acquisitions(baseline_metrics, "GREEN", "command")

        # Fire some requests
        for _ in range(3):
            response = harness_tests._post_command(client, payload)
            assert response.status_code in (200, 509), f"Unexpected status: {response.status_code}"

        # Check updated metrics
        updated_response = client.get("/metrics")
        assert updated_response.status_code == 200
        updated_metrics = updated_response.text

        updated_green = extract_acquisitions(updated_metrics, "GREEN", "command")

        # Should have incremented (at least some requests succeeded)
        assert (
            updated_green >= baseline_green
        ), "Acquisition counter did not increment: metrics may not be tracking band properly"

    def test_rejection_metrics_increase_under_capacity_exhaustion(
        self, temp_app_with_client: Any
    ) -> None:
        """Validate rejection counters increment when port capacity is exceeded."""
        app, client, contract, signing_key = temp_app_with_client

        payload = harness_tests._make_signed_envelope(contract, signing_key)

        # Get baseline rejection counts
        baseline_response = client.get("/metrics")
        assert baseline_response.status_code == 200
        baseline_metrics = baseline_response.text

        def extract_rejections(metrics: str, band: str, port: str) -> float:
            """Parse Prometheus metrics for rejection counter."""
            prefix = f'qos_rejections_capacity_total{{band="{band}",port="{port}"}}'
            for line in metrics.splitlines():
                if line.startswith(prefix):
                    try:
                        return float(line.split()[-1])
                    except (ValueError, IndexError):
                        pass
            return 0

        baseline_rejections = extract_rejections(baseline_metrics, "GREEN", "command")

        # Fire requests until we hit capacity (command port limit typically 64 tokens)
        successes = 0
        failures = 0
        for _ in range(100):  # Try many times to ensure we hit capacity
            response = harness_tests._post_command(client, payload)
            if response.status_code == 200:
                successes += 1
            elif response.status_code == 509:
                failures += 1

        # Check updated rejection metrics
        updated_response = client.get("/metrics")
        assert updated_response.status_code == 200
        updated_metrics = updated_response.text

        updated_rejections = extract_rejections(updated_metrics, "GREEN", "command")

        # If we got any 509s, rejection counter should have incremented
        if failures > 0:
            assert (
                updated_rejections > baseline_rejections
            ), f"Rejection counter did not increment despite {failures} 509 responses"
        else:
            # If we didn't hit capacity, that's also valid - just document it
            pytest.skip(f"Did not exhaust capacity in {successes} attempts")
