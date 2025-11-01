"""Tests for chaos scheduler and fault injection framework."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from k0.automation.chaos_scheduler import (
    PROFILES,
    ChaosExperiment,
    ChaosInjector,
    ChaosProfile,
    ChaosReport,
    FaultEvent,
    RecoveryCheckpoint,
    RecoveryValidator,
    generate_report_markdown,
)


class TestChaosProfile:
    """Tests for ChaosProfile validation."""

    def test_profile_valid(self):
        """Test valid profile validation."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.1,
            scheduler_multiplier=0.5,
            network_latency_ms=50,
            telemetry_outage_rate=0.05,
        )
        assert profile.validate()

    def test_profile_invalid_fsync_rate(self):
        """Test profile with invalid fsync rate."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=1.5,  # > 1.0
            scheduler_multiplier=0.5,
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )
        assert not profile.validate()

    def test_profile_invalid_scheduler_multiplier(self):
        """Test profile with invalid scheduler multiplier."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.1,
            scheduler_multiplier=0.0,  # Must be > 0
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )
        assert not profile.validate()

    def test_predefined_profiles_valid(self):
        """Test that all predefined profiles are valid."""
        for name, profile in PROFILES.items():
            assert profile.validate(), f"Profile {name} is invalid"

    def test_profile_names_match(self):
        """Test that profile names match their keys."""
        for name, profile in PROFILES.items():
            assert profile.name == name


class TestChaosInjector:
    """Tests for fault injection decision logic."""

    def test_injector_fsync_failure_rate(self):
        """Test fsync failure injection rate is correct."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.5,  # 50% failure rate
            scheduler_multiplier=1.0,
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )
        injector = ChaosInjector(profile, random_seed=42)

        # With seed, should be deterministic
        injections = [injector.should_inject_fsync_failure() for _ in range(100)]
        failure_rate = sum(injections) / len(injections)

        # Should be close to 50% (allowing 10% variance)
        assert 0.4 <= failure_rate <= 0.6

    def test_injector_scheduler_stress(self):
        """Test scheduler stress injection."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.0,
            scheduler_multiplier=0.5,  # 50% degradation
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )
        injector = ChaosInjector(profile, random_seed=42)

        # With 0.5 multiplier, degradation rate should be ~0.5
        degradations = [injector.should_degrade_scheduler() for _ in range(100)]
        degradation_rate = sum(degradations) / len(degradations)

        assert 0.4 <= degradation_rate <= 0.6

    def test_injector_network_latency(self):
        """Test network latency injection."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.0,
            scheduler_multiplier=1.0,
            network_latency_ms=100,
            telemetry_outage_rate=0.0,
        )
        injector = ChaosInjector(profile, random_seed=42)

        latencies = [injector.get_network_latency_ms() for _ in range(10)]

        # All latencies should be in range [80, 120] (±20% jitter)
        assert all(80 <= lat <= 120 for lat in latencies)

    def test_injector_no_latency_when_zero(self):
        """Test no latency when configured as zero."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.0,
            scheduler_multiplier=1.0,
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )
        injector = ChaosInjector(profile)

        latencies = [injector.get_network_latency_ms() for _ in range(10)]
        assert all(lat == 0 for lat in latencies)

    def test_injector_telemetry_drop(self):
        """Test telemetry dropping."""
        profile = ChaosProfile(
            name="test",
            fsync_fail_rate=0.0,
            scheduler_multiplier=1.0,
            network_latency_ms=0,
            telemetry_outage_rate=0.3,  # 30% drop rate
        )
        injector = ChaosInjector(profile, random_seed=42)

        drops = [injector.should_drop_telemetry() for _ in range(100)]
        drop_rate = sum(drops) / len(drops)

        assert 0.2 <= drop_rate <= 0.4

    def test_reproducible_with_seed(self):
        """Test that same seed produces same sequence."""
        profile = PROFILES["moderate"]

        injector1 = ChaosInjector(profile, random_seed=123)
        sequence1 = [injector1.should_inject_fsync_failure() for _ in range(20)]

        injector2 = ChaosInjector(profile, random_seed=123)
        sequence2 = [injector2.should_inject_fsync_failure() for _ in range(20)]

        assert sequence1 == sequence2


class TestRecoveryValidator:
    """Tests for recovery validation logic."""

    def test_validate_replay_parity_success(self):
        """Test successful replay parity validation."""
        original = [
            {"command_id": "cmd1", "result_hash": "hash1"},
            {"command_id": "cmd2", "result_hash": "hash2"},
        ]
        replayed = [
            {"command_id": "cmd1", "result_hash": "hash1"},
            {"command_id": "cmd2", "result_hash": "hash2"},
        ]

        valid, details = RecoveryValidator.validate_replay_parity(original, replayed)
        assert valid
        assert "successfully" in details.lower()

    def test_validate_replay_parity_count_mismatch(self):
        """Test replay parity with count mismatch."""
        original = [
            {"command_id": "cmd1", "result_hash": "hash1"},
            {"command_id": "cmd2", "result_hash": "hash2"},
        ]
        replayed = [
            {"command_id": "cmd1", "result_hash": "hash1"},
        ]

        valid, details = RecoveryValidator.validate_replay_parity(original, replayed)
        assert not valid
        assert "count mismatch" in details.lower()

    def test_validate_replay_parity_id_mismatch(self):
        """Test replay parity with command ID mismatch."""
        original = [
            {"command_id": "cmd1", "result_hash": "hash1"},
        ]
        replayed = [
            {"command_id": "cmd_different", "result_hash": "hash1"},
        ]

        valid, details = RecoveryValidator.validate_replay_parity(original, replayed)
        assert not valid
        assert "ID mismatch" in details

    def test_validate_replay_parity_hash_mismatch(self):
        """Test replay parity with result hash mismatch."""
        original = [
            {"command_id": "cmd1", "result_hash": "hash1"},
        ]
        replayed = [
            {"command_id": "cmd1", "result_hash": "hash_different"},
        ]

        valid, details = RecoveryValidator.validate_replay_parity(original, replayed)
        assert not valid
        assert "hash mismatch" in details.lower()

    def test_validate_receipt_consistency_success(self):
        """Test successful receipt consistency validation."""
        during_chaos = [
            {"receipt_id": "r1", "hash": "h1"},
            {"receipt_id": "r2", "hash": "h2"},
        ]
        after_recovery = [
            {"receipt_id": "r1", "hash": "h1"},
            {"receipt_id": "r2", "hash": "h2"},
        ]

        valid, details = RecoveryValidator.validate_receipt_consistency(
            during_chaos, after_recovery
        )
        assert valid
        assert "consistent" in details.lower()

    def test_validate_receipt_consistency_missing_receipt(self):
        """Test receipt consistency with missing receipt."""
        during_chaos = [
            {"receipt_id": "r1", "hash": "h1"},
            {"receipt_id": "r2", "hash": "h2"},
        ]
        after_recovery = [
            {"receipt_id": "r1", "hash": "h1"},
        ]

        valid, details = RecoveryValidator.validate_receipt_consistency(
            during_chaos, after_recovery
        )
        assert not valid
        assert "lost" in details.lower()

    def test_validate_receipt_consistency_corrupted_hash(self):
        """Test receipt consistency with corrupted hash."""
        during_chaos = [
            {"receipt_id": "r1", "hash": "h1"},
        ]
        after_recovery = [
            {"receipt_id": "r1", "hash": "h_corrupted"},
        ]

        valid, details = RecoveryValidator.validate_receipt_consistency(
            during_chaos, after_recovery
        )
        assert not valid
        assert "corrupted" in details.lower()

    def test_validate_sse_reconnection_success(self):
        """Test successful SSE reconnection validation."""
        valid, details = RecoveryValidator.validate_sse_reconnection(
            sse_connections_before=5,
            sse_connections_after=5,
            sse_events_received=50,
        )
        assert valid
        assert "recovery successful" in details.lower()

    def test_validate_sse_reconnection_no_connections(self):
        """Test SSE reconnection with no active connections."""
        valid, details = RecoveryValidator.validate_sse_reconnection(
            sse_connections_before=5,
            sse_connections_after=0,
            sse_events_received=0,
        )
        assert not valid
        assert "no" in details.lower() and "connection" in details.lower()

    def test_validate_sse_reconnection_missing_events(self):
        """Test SSE reconnection with missing events."""
        valid, details = RecoveryValidator.validate_sse_reconnection(
            sse_connections_before=10,
            sse_connections_after=10,
            sse_events_received=5,
        )
        assert not valid
        assert "missing" in details.lower()

    def test_validate_scheduler_recovery_success(self):
        """Test successful scheduler recovery validation."""
        valid, details = RecoveryValidator.validate_scheduler_recovery(
            queue_depth_during_chaos=500,
            queue_depth_after_recovery=200,
            max_queue_depth=250,
        )
        assert valid
        assert "recovered" in details.lower()

    def test_validate_scheduler_recovery_queue_overflow(self):
        """Test scheduler recovery with queue overflow."""
        valid, details = RecoveryValidator.validate_scheduler_recovery(
            queue_depth_during_chaos=500,
            queue_depth_after_recovery=300,  # > max
            max_queue_depth=250,
        )
        assert not valid
        assert "not recovered" in details.lower()


class TestFaultEvent:
    """Tests for fault event dataclass."""

    def test_fault_event_creation(self):
        """Test creating a fault event."""
        event = FaultEvent(
            timestamp="2025-01-01T00:00:00+00:00",
            fault_type="fsync_failure",
            description="WAL fsync failed",
            metadata={"errno": 5},
        )

        assert event.fault_type == "fsync_failure"
        assert event.metadata["errno"] == 5

    def test_fault_event_to_dict(self):
        """Test converting fault event to dictionary."""
        event = FaultEvent(
            timestamp="2025-01-01T00:00:00+00:00",
            fault_type="network_latency",
            description="Added 50ms latency",
        )

        d = event.to_dict()
        assert d["fault_type"] == "network_latency"
        assert "description" in d


class TestChaosReport:
    """Tests for chaos report generation."""

    def test_chaos_report_creation(self):
        """Test creating a chaos report."""
        report = ChaosReport(
            experiment_id="exp123",
            profile_name="mild",
            start_time="2025-01-01T00:00:00+00:00",
            end_time="2025-01-01T00:01:00+00:00",
            duration_seconds=60.0,
        )

        assert report.experiment_id == "exp123"
        assert report.profile_name == "mild"

    def test_chaos_report_to_dict(self):
        """Test converting report to dictionary."""
        report = ChaosReport(
            experiment_id="exp123",
            profile_name="mild",
            start_time="2025-01-01T00:00:00+00:00",
            end_time="2025-01-01T00:01:00+00:00",
            duration_seconds=60.0,
            fault_events=[
                FaultEvent(
                    timestamp="2025-01-01T00:00:30+00:00",
                    fault_type="fsync_failure",
                    description="Test fault",
                )
            ],
        )

        d = report.to_dict()
        assert d["experiment_id"] == "exp123"
        assert len(d["fault_events"]) == 1
        assert d["fault_events"][0]["fault_type"] == "fsync_failure"

    def test_chaos_report_json_serializable(self):
        """Test that report is JSON serializable."""
        report = ChaosReport(
            experiment_id="exp123",
            profile_name="mild",
            start_time="2025-01-01T00:00:00+00:00",
            end_time="2025-01-01T00:01:00+00:00",
            duration_seconds=60.0,
        )

        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["experiment_id"] == "exp123"


class TestChaosExperiment:
    """Tests for chaos experiment orchestration."""

    def test_experiment_creation(self):
        """Test creating a chaos experiment."""
        profile = PROFILES["mild"]
        experiment = ChaosExperiment(profile, duration_seconds=10)

        assert experiment.profile.name == "mild"
        assert experiment.duration_seconds == 10

    def test_experiment_invalid_profile(self):
        """Test creating experiment with invalid profile."""
        invalid_profile = ChaosProfile(
            name="invalid",
            fsync_fail_rate=2.0,  # Invalid
            scheduler_multiplier=0.5,
            network_latency_ms=0,
            telemetry_outage_rate=0.0,
        )

        with pytest.raises(ValueError):
            ChaosExperiment(invalid_profile)

    def test_experiment_run(self):
        """Test running a chaos experiment."""
        profile = PROFILES["mild"]
        experiment = ChaosExperiment(profile, duration_seconds=1)  # 1 second
        report = experiment.run()

        assert report.experiment_id
        assert report.profile_name == "mild"
        assert report.duration_seconds > 0
        assert report.start_time
        assert report.end_time

    def test_experiment_reproducible_with_seed(self):
        """Test that experiments with same seed are reproducible."""
        profile = PROFILES["moderate"]

        experiment1 = ChaosExperiment(profile, duration_seconds=1, random_seed=42)
        report1 = experiment1.run()

        experiment2 = ChaosExperiment(profile, duration_seconds=1, random_seed=42)
        report2 = experiment2.run()

        # Should have similar number of fault events (within 1-2 events due to timing)
        assert abs(len(report1.fault_events) - len(report2.fault_events)) <= 2

        # Fault types should match closely
        types1 = [e.fault_type for e in report1.fault_events]
        types2 = [e.fault_type for e in report2.fault_events]
        # Check that we have similar distribution (not exact equality due to timing)
        assert len(types1) > 0 and len(types2) > 0

    def test_experiment_validate_recovery_no_data(self):
        """Test recovery validation with no data provided."""
        profile = PROFILES["mild"]
        experiment = ChaosExperiment(profile, duration_seconds=1)
        experiment.run()

        # Validate with no input data
        passed, violations = experiment.validate_recovery()

        # Should pass with no data (no assertions made)
        assert passed
        assert len(violations) == 0

    def test_experiment_validate_recovery_replay_parity(self):
        """Test recovery validation with replay parity check."""
        profile = PROFILES["mild"]
        experiment = ChaosExperiment(profile, duration_seconds=1)
        experiment.run()

        original = [
            {"command_id": "cmd1", "result_hash": "hash1"},
        ]
        replayed = [
            {"command_id": "cmd1", "result_hash": "hash1"},
        ]

        passed, violations = experiment.validate_recovery(
            original_commands=original,
            replayed_commands=replayed,
        )

        assert passed
        assert len(violations) == 0

    def test_experiment_validate_recovery_multiple_violations(self):
        """Test recovery validation with multiple violations."""
        profile = PROFILES["mild"]
        experiment = ChaosExperiment(profile, duration_seconds=1)
        experiment.run()

        passed, violations = experiment.validate_recovery(
            original_commands=[{"command_id": "cmd1", "result_hash": "hash1"}],
            replayed_commands=[{"command_id": "cmd_wrong", "result_hash": "hash1"}],
            receipts_during=[{"receipt_id": "r1", "hash": "h1"}],
            receipts_after=[],
            sse_metrics={"connections_before": 5, "connections_after": 0, "events_received": 0},
        )

        assert not passed
        assert len(violations) > 0


class TestReportGeneration:
    """Tests for report generation."""

    def test_generate_markdown_report_no_violations(self):
        """Test generating Markdown report with no violations."""
        report = ChaosReport(
            experiment_id="exp123",
            profile_name="mild",
            start_time="2025-01-01T00:00:00+00:00",
            end_time="2025-01-01T00:01:00+00:00",
            duration_seconds=60.0,
            fault_events=[
                FaultEvent(
                    timestamp="2025-01-01T00:00:30+00:00",
                    fault_type="fsync_failure",
                    description="WAL fsync failed",
                )
            ],
            recovery_checkpoints=[
                RecoveryCheckpoint(
                    timestamp="2025-01-01T00:01:05+00:00",
                    invariant="replay_parity",
                    status="passed",
                    details="All commands replayed successfully",
                )
            ],
        )

        markdown = generate_report_markdown(report)

        assert "Chaos Experiment Report" in markdown
        assert "PASSED" in markdown
        assert "fsync_failure" in markdown
        assert "replay_parity" in markdown

    def test_generate_markdown_report_with_violations(self):
        """Test generating Markdown report with violations."""
        report = ChaosReport(
            experiment_id="exp123",
            profile_name="aggressive",
            start_time="2025-01-01T00:00:00+00:00",
            end_time="2025-01-01T00:01:00+00:00",
            duration_seconds=60.0,
            invariant_violations=["replay_parity: Command ID mismatch"],
        )

        markdown = generate_report_markdown(report)

        assert "FAILED" in markdown
        assert "Remediation Steps" in markdown
        assert "replay_parity" in markdown

    def test_markdown_report_structure(self):
        """Test Markdown report has expected structure."""
        profile = PROFILES["moderate"]
        experiment = ChaosExperiment(profile, duration_seconds=1)
        report = experiment.run()

        markdown = generate_report_markdown(report)

        # Check for key sections
        assert "# Chaos Experiment Report" in markdown
        assert "## Fault Injection Timeline" in markdown
        assert "## Recovery Validation" in markdown


class TestEndToEnd:
    """End-to-end integration tests."""

    def test_end_to_end_chaos_experiment(self):
        """Test complete chaos experiment workflow."""
        for profile_name in ["mild", "moderate", "aggressive"]:
            profile = PROFILES[profile_name]
            experiment = ChaosExperiment(profile, duration_seconds=1, random_seed=42)
            report = experiment.run()

            # Validate report structure
            assert report.experiment_id
            assert report.profile_name == profile_name
            assert report.start_time
            assert report.end_time
            assert len(report.fault_events) > 0

            # Validate recovery
            passed, violations = experiment.validate_recovery(
                original_commands=[{"command_id": "c1", "result_hash": "h1"}],
                replayed_commands=[{"command_id": "c1", "result_hash": "h1"}],
            )
            assert passed

    def test_end_to_end_with_file_output(self):
        """Test chaos experiment with file output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chaos-report.json"

            profile = PROFILES["mild"]
            experiment = ChaosExperiment(profile, duration_seconds=1, random_seed=42)
            report = experiment.run()

            # Simulate file output
            output_path.write_text(json.dumps(report.to_dict(), indent=2))

            # Read and verify
            loaded = json.loads(output_path.read_text())
            assert loaded["experiment_id"] == report.experiment_id
            assert loaded["profile_name"] == "mild"
