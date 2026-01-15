"""
Test suite for P03 Retention Service.

Tests the retention wiring for audit records including
90-day retention, aggregation, and maintenance jobs.

Spec Reference: Dossier §6.20 Retention Policy
"""

from __future__ import annotations

import time
import uuid

import pytest

from k0.pipelines.p03.retention import (
    DEFAULT_RETENTION_DAYS,
    MS_PER_DAY,
    DailyAuditSummary,
    InMemoryRetentionRepository,
    RetentionJobResult,
    RetentionService,
    aggregate_records_to_daily_summaries,
    create_retention_service,
    get_retention_policy_config,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def repository() -> InMemoryRetentionRepository:
    """Create a fresh in-memory repository."""
    return InMemoryRetentionRepository()


@pytest.fixture
def service(repository: InMemoryRetentionRepository) -> RetentionService:
    """Create a retention service with default settings."""
    return RetentionService(repository, retention_days=90)


@pytest.fixture
def old_timestamp() -> int:
    """Timestamp 100 days ago (beyond retention)."""
    return int(time.time() * 1000) - (100 * MS_PER_DAY)


@pytest.fixture
def recent_timestamp() -> int:
    """Timestamp 10 days ago (within retention)."""
    return int(time.time() * 1000) - (10 * MS_PER_DAY)


def make_audit_record(
    created_at: int,
    space_id: str = "space_1",
    tenant_id: str = "tenant_1",
    action: str = "REINFORCE",
    confidence: float | None = 0.85,
) -> dict:
    """Helper to create an audit record."""
    return {
        "audit_id": str(uuid.uuid4()),
        "memory_id": f"mem_{uuid.uuid4().hex[:8]}",
        "space_id": space_id,
        "tenant_id": tenant_id,
        "action": action,
        "explanation": f"Action {action} performed",
        "confidence": confidence,
        "created_at": created_at,
        "formula_used": "cosine_similarity",
    }


# =============================================================================
# TEST CLASS: DailyAuditSummary Dataclass
# =============================================================================


class TestDailyAuditSummary:
    """Tests for the DailyAuditSummary dataclass."""

    def test_summary_creation(self):
        """Test creating a summary with basic fields."""
        summary = DailyAuditSummary(
            summary_date="2024-01-15",
            space_id="space_1",
            tenant_id="tenant_1",
            action_counts={"REINFORCE": 10, "DECAY": 5},
            total_records=15,
            avg_confidence=0.75,
        )

        assert summary.summary_date == "2024-01-15"
        assert summary.total_records == 15
        assert summary.action_counts["REINFORCE"] == 10

    def test_summary_to_dict(self):
        """Test converting summary to dictionary."""
        summary = DailyAuditSummary(
            summary_date="2024-01-15",
            space_id="space_1",
            tenant_id="tenant_1",
            action_counts={"REINFORCE": 10},
            total_records=10,
            avg_confidence=0.85,
            min_confidence=0.7,
            max_confidence=0.95,
        )

        result = summary.to_dict()

        assert result["summary_date"] == "2024-01-15"
        assert result["total_records"] == 10
        assert result["avg_confidence"] == 0.85
        assert result["min_confidence"] == 0.7
        assert result["max_confidence"] == 0.95

    def test_summary_defaults(self):
        """Test default values for optional fields."""
        summary = DailyAuditSummary(
            summary_date="2024-01-15",
            space_id="space_1",
            tenant_id="tenant_1",
        )

        assert summary.action_counts == {}
        assert summary.total_records == 0
        assert summary.avg_confidence is None
        assert summary.formula_counts == {}


# =============================================================================
# TEST CLASS: RetentionJobResult Dataclass
# =============================================================================


class TestRetentionJobResult:
    """Tests for the RetentionJobResult dataclass."""

    def test_result_creation(self):
        """Test creating a job result."""
        result = RetentionJobResult(
            cutoff_timestamp_ms=1000000,
            job_started_at=2000000,
        )

        assert result.cutoff_timestamp_ms == 1000000
        assert result.records_scanned == 0
        assert result.records_deleted == 0
        assert result.success is True

    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = RetentionJobResult(
            cutoff_timestamp_ms=1000000,
            job_started_at=2000000,
            job_completed_at=3000000,
        )
        result.records_scanned = 100
        result.records_deleted = 50
        result.summaries_created = 5

        data = result.to_dict()

        assert data["records_scanned"] == 100
        assert data["records_deleted"] == 50
        assert data["summaries_created"] == 5
        assert data["success"] is True


# =============================================================================
# TEST CLASS: InMemoryRetentionRepository
# =============================================================================


class TestInMemoryRetentionRepository:
    """Tests for the in-memory retention repository."""

    def test_repository_starts_empty(self, repository: InMemoryRetentionRepository):
        """Test repository starts with no records."""
        records = repository.get_records_before_cutoff(int(time.time() * 1000))
        assert records == []

    def test_add_and_retrieve_records(
        self,
        repository: InMemoryRetentionRepository,
        old_timestamp: int,
    ):
        """Test adding and retrieving records."""
        record = make_audit_record(old_timestamp)
        repository.add_record(record)

        # Get records older than now
        records = repository.get_records_before_cutoff(int(time.time() * 1000))
        assert len(records) == 1

    def test_cutoff_filtering(
        self,
        repository: InMemoryRetentionRepository,
        old_timestamp: int,
        recent_timestamp: int,
    ):
        """Test that cutoff properly filters records."""
        # Add old record
        repository.add_record(make_audit_record(old_timestamp))
        # Add recent record
        repository.add_record(make_audit_record(recent_timestamp))

        # Cutoff 50 days ago - should only get old record
        cutoff = int(time.time() * 1000) - (50 * MS_PER_DAY)
        records = repository.get_records_before_cutoff(cutoff)

        assert len(records) == 1
        assert records[0]["created_at"] == old_timestamp

    def test_delete_records_by_ids(
        self,
        repository: InMemoryRetentionRepository,
        old_timestamp: int,
    ):
        """Test deleting records by IDs."""
        record1 = make_audit_record(old_timestamp)
        record2 = make_audit_record(old_timestamp)
        repository.add_record(record1)
        repository.add_record(record2)

        # Delete first record
        deleted = repository.delete_records_by_ids([record1["audit_id"]])

        assert deleted == 1
        remaining = repository.get_records_before_cutoff(int(time.time() * 1000))
        assert len(remaining) == 1
        assert remaining[0]["audit_id"] == record2["audit_id"]

    def test_batch_size_limit(
        self,
        repository: InMemoryRetentionRepository,
        old_timestamp: int,
    ):
        """Test batch_size limits returned records."""
        # Add 10 records
        for _ in range(10):
            repository.add_record(make_audit_record(old_timestamp))

        # Get with batch_size=3
        records = repository.get_records_before_cutoff(
            int(time.time() * 1000),
            batch_size=3,
        )

        assert len(records) == 3

    def test_save_daily_summary(self, repository: InMemoryRetentionRepository):
        """Test saving a daily summary."""
        summary = DailyAuditSummary(
            summary_date="2024-01-15",
            space_id="space_1",
            tenant_id="tenant_1",
            total_records=10,
        )

        result = repository.save_daily_summary(summary)

        assert result is True
        assert len(repository.get_summaries()) == 1

    def test_summary_exists_check(self, repository: InMemoryRetentionRepository):
        """Test checking if summary exists."""
        summary = DailyAuditSummary(
            summary_date="2024-01-15",
            space_id="space_1",
            tenant_id="tenant_1",
        )
        repository.save_daily_summary(summary)

        # Same date/space/tenant should exist
        assert repository.summary_exists("2024-01-15", "space_1", "tenant_1") is True
        # Different date should not exist
        assert repository.summary_exists("2024-01-16", "space_1", "tenant_1") is False
        # Different space should not exist
        assert repository.summary_exists("2024-01-15", "space_2", "tenant_1") is False


# =============================================================================
# TEST CLASS: aggregate_records_to_daily_summaries
# =============================================================================


class TestAggregation:
    """Tests for the aggregation function."""

    def test_aggregate_empty_list(self):
        """Test aggregating empty list returns empty."""
        result = aggregate_records_to_daily_summaries([])
        assert result == []

    def test_aggregate_single_record(self):
        """Test aggregating a single record."""
        # Use fixed timestamp for predictable date
        fixed_ts = 1705320000000  # 2024-01-15 12:00:00 UTC
        records = [make_audit_record(fixed_ts)]

        summaries = aggregate_records_to_daily_summaries(records)

        assert len(summaries) == 1
        assert summaries[0].summary_date == "2024-01-15"
        assert summaries[0].total_records == 1

    def test_aggregate_groups_by_date(self):
        """Test records are grouped by date."""
        day1_ts = 1705320000000  # 2024-01-15
        day2_ts = day1_ts + MS_PER_DAY  # 2024-01-16

        records = [
            make_audit_record(day1_ts),
            make_audit_record(day1_ts),
            make_audit_record(day2_ts),
        ]

        summaries = aggregate_records_to_daily_summaries(records)

        # Should have 2 summaries (one per day)
        assert len(summaries) == 2
        dates = {s.summary_date for s in summaries}
        assert "2024-01-15" in dates
        assert "2024-01-16" in dates

    def test_aggregate_groups_by_space(self):
        """Test records are grouped by space."""
        fixed_ts = 1705320000000
        records = [
            make_audit_record(fixed_ts, space_id="space_1"),
            make_audit_record(fixed_ts, space_id="space_2"),
        ]

        summaries = aggregate_records_to_daily_summaries(records)

        assert len(summaries) == 2
        spaces = {s.space_id for s in summaries}
        assert spaces == {"space_1", "space_2"}

    def test_aggregate_counts_actions(self):
        """Test action counts are computed correctly."""
        fixed_ts = 1705320000000
        records = [
            make_audit_record(fixed_ts, action="REINFORCE"),
            make_audit_record(fixed_ts, action="REINFORCE"),
            make_audit_record(fixed_ts, action="DECAY"),
        ]

        summaries = aggregate_records_to_daily_summaries(records)

        assert len(summaries) == 1
        assert summaries[0].action_counts["REINFORCE"] == 2
        assert summaries[0].action_counts["DECAY"] == 1

    def test_aggregate_computes_confidence_stats(self):
        """Test confidence statistics are computed."""
        fixed_ts = 1705320000000
        records = [
            make_audit_record(fixed_ts, confidence=0.6),
            make_audit_record(fixed_ts, confidence=0.8),
            make_audit_record(fixed_ts, confidence=1.0),
        ]

        summaries = aggregate_records_to_daily_summaries(records)

        assert len(summaries) == 1
        assert summaries[0].min_confidence == 0.6
        assert summaries[0].max_confidence == 1.0
        assert summaries[0].avg_confidence == pytest.approx(0.8, abs=0.01)

    def test_aggregate_handles_null_confidence(self):
        """Test handling records with null confidence."""
        fixed_ts = 1705320000000
        records = [
            make_audit_record(fixed_ts, confidence=0.8),
            make_audit_record(fixed_ts, confidence=None),
        ]

        summaries = aggregate_records_to_daily_summaries(records)

        # Should only consider non-null confidences
        assert summaries[0].avg_confidence == 0.8
        assert summaries[0].total_records == 2


# =============================================================================
# TEST CLASS: RetentionService
# =============================================================================


class TestRetentionService:
    """Tests for the RetentionService."""

    def test_calculate_cutoff_timestamp(self, service: RetentionService):
        """Test cutoff timestamp calculation."""
        now_ms = 1705320000000  # Fixed timestamp
        cutoff = service.calculate_cutoff_timestamp(now_ms)

        expected = now_ms - (90 * MS_PER_DAY)
        assert cutoff == expected

    def test_run_maintenance_empty_repo(self, service: RetentionService):
        """Test maintenance job on empty repository."""
        result = service.run_maintenance()

        assert result.success is True
        assert result.records_scanned == 0
        assert result.records_deleted == 0
        assert result.summaries_created == 0

    def test_run_maintenance_deletes_old_records(
        self,
        repository: InMemoryRetentionRepository,
        service: RetentionService,
        old_timestamp: int,
    ):
        """Test that old records are deleted after aggregation."""
        # Add old record
        repository.add_record(make_audit_record(old_timestamp))

        result = service.run_maintenance()

        assert result.success is True
        assert result.records_deleted == 1

        # Verify record is gone
        remaining = repository.get_records_before_cutoff(int(time.time() * 1000))
        assert len(remaining) == 0

    def test_run_maintenance_preserves_recent_records(
        self,
        repository: InMemoryRetentionRepository,
        service: RetentionService,
        recent_timestamp: int,
    ):
        """Test that recent records are preserved."""
        repository.add_record(make_audit_record(recent_timestamp))

        result = service.run_maintenance()

        assert result.records_deleted == 0

        # Record should still exist
        remaining = repository.get_records_before_cutoff(int(time.time() * 1000))
        assert len(remaining) == 1

    def test_run_maintenance_creates_summaries(
        self,
        repository: InMemoryRetentionRepository,
        service: RetentionService,
        old_timestamp: int,
    ):
        """Test that summaries are created before deletion."""
        repository.add_record(make_audit_record(old_timestamp))

        result = service.run_maintenance()

        assert result.summaries_created >= 1
        assert len(repository.get_summaries()) >= 1

    def test_run_maintenance_is_idempotent(
        self,
        repository: InMemoryRetentionRepository,
        service: RetentionService,
        old_timestamp: int,
    ):
        """Test that running maintenance twice is safe."""
        repository.add_record(make_audit_record(old_timestamp))

        # First run
        result1 = service.run_maintenance()

        # Second run (should not create duplicate summaries)
        result2 = service.run_maintenance()

        # First run creates summary, second finds no records
        assert result1.summaries_created >= 1
        assert result2.records_scanned == 0
        assert result2.summaries_created == 0

        # Only one summary should exist
        assert len(repository.get_summaries()) >= 1

    def test_run_maintenance_handles_multiple_spaces(
        self,
        repository: InMemoryRetentionRepository,
        service: RetentionService,
        old_timestamp: int,
    ):
        """Test handling records from multiple spaces."""
        repository.add_record(make_audit_record(old_timestamp, space_id="space_1"))
        repository.add_record(make_audit_record(old_timestamp, space_id="space_2"))

        result = service.run_maintenance()

        assert result.success is True
        assert result.records_deleted == 2
        # Should have summaries for both spaces
        assert result.summaries_created == 2


# =============================================================================
# TEST CLASS: Factory and Config Functions
# =============================================================================


class TestFactoryAndConfig:
    """Tests for factory and configuration functions."""

    def test_create_retention_service(
        self,
        repository: InMemoryRetentionRepository,
    ):
        """Test creating service via factory function."""
        service = create_retention_service(repository, retention_days=30)

        assert isinstance(service, RetentionService)

    def test_create_retention_service_custom_retention(
        self,
        repository: InMemoryRetentionRepository,
    ):
        """Test custom retention days."""
        service = create_retention_service(repository, retention_days=30)

        now_ms = 1705320000000
        cutoff = service.calculate_cutoff_timestamp(now_ms)

        expected = now_ms - (30 * MS_PER_DAY)
        assert cutoff == expected

    def test_get_retention_policy_config(self):
        """Test getting retention policy configuration."""
        config = get_retention_policy_config()

        assert config["policy_name"] == "consolidation_audit_retention"
        assert config["resource_type"] == "st_consolidation_audit"
        assert config["retention_days"] == DEFAULT_RETENTION_DAYS
        assert config["privacy_band"] == "AMBER"
        assert config["archive_enabled"] is True


# =============================================================================
# TEST CLASS: Constants
# =============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_default_retention_days(self):
        """Test default retention is 90 days."""
        assert DEFAULT_RETENTION_DAYS == 90

    def test_ms_per_day(self):
        """Test milliseconds per day calculation."""
        expected = 24 * 60 * 60 * 1000
        assert MS_PER_DAY == expected
