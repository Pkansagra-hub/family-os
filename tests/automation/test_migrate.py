"""Tests for migrate module.

Tests cover:
- Migration result dataclass
- Current revision retrieval
- Pending migrations detection
- Migration application (dry-run and actual)
- Migration rollback
- Migration history retrieval
- Error handling for missing config and failed migrations
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from k0.automation.migrate import (
    MigrationError,
    MigrationResult,
    apply_migrations,
    get_current_revision,
    get_migration_history,
    get_pending_revisions,
    rollback_migration,
)


@pytest.fixture
def temp_alembic_ini():
    """Create temporary alembic.ini file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
        f.write(
            """[alembic]
script_location = k0/db/alembic
sqlalchemy.url = postgresql://test:test@localhost/test

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = WARN
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""
        )
        f.flush()
        yield Path(f.name)
    Path(f.name).unlink()


class TestMigrationResult:
    """Tests for MigrationResult dataclass."""

    def test_migration_result_creation(self):
        """Test creating a MigrationResult instance."""
        result = MigrationResult(
            revision="abc123",
            action="applied",
            description="Add user table",
            duration_seconds=1.5,
        )

        assert result.revision == "abc123"
        assert result.action == "applied"
        assert result.description == "Add user table"
        assert result.duration_seconds == 1.5

    def test_migration_result_optional_duration(self):
        """Test MigrationResult with None duration."""
        result = MigrationResult(
            revision="def456",
            action="skipped",
            description="Already applied",
        )

        assert result.revision == "def456"
        assert result.action == "skipped"
        assert result.duration_seconds is None


class TestGetCurrentRevision:
    """Tests for get_current_revision function."""

    def test_get_current_revision_success(self, temp_alembic_ini):
        """Test successful current revision retrieval."""
        mock_config = Mock()
        mock_config.output_buffer.getvalue.return_value = "abc123 (head)\n"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.current"),
        ):
            mock_get_config.return_value = mock_config

            result = get_current_revision(temp_alembic_ini)
            assert result == "abc123"

    def test_get_current_revision_different_format(self, temp_alembic_ini):
        """Test current revision with different output format."""
        mock_config = Mock()
        mock_config.output_buffer.getvalue.return_value = "def456\n"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.current"),
        ):
            mock_get_config.return_value = mock_config

            result = get_current_revision(temp_alembic_ini)
            assert result == "def456"

    def test_get_current_revision_none(self, temp_alembic_ini):
        """Test current revision when no migrations applied."""
        mock_config = Mock()
        mock_config.output_buffer.getvalue.return_value = ""

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.current"),
        ):
            mock_get_config.return_value = mock_config

            result = get_current_revision(temp_alembic_ini)
            assert result is None

    def test_get_current_revision_error(self, temp_alembic_ini):
        """Test current revision retrieval failure."""
        mock_config = Mock()

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.current") as mock_current,
        ):
            mock_get_config.return_value = mock_config
            mock_current.side_effect = Exception("Config error")

            with pytest.raises(MigrationError, match="Failed to get current revision"):
                get_current_revision(temp_alembic_ini)

    def test_get_current_revision_config_not_found(self):
        """Test current revision when alembic.ini not found."""
        nonexistent_path = Path("/nonexistent/alembic.ini")

        with pytest.raises(MigrationError, match="Alembic config not found"):
            get_current_revision(nonexistent_path)


class TestGetPendingRevisions:
    """Tests for get_pending_revisions function."""

    def test_get_pending_revisions_with_pending(self, temp_alembic_ini):
        """Test getting pending revisions when some exist."""
        mock_script = Mock()
        mock_revision1 = Mock()
        mock_revision1.revision = "def456"
        mock_revision1.doc = "Add user table"
        mock_revision2 = Mock()
        mock_revision2.revision = "ghi789"
        mock_revision2.doc = "Add product table"

        mock_script.iterate_revisions.return_value = [
            mock_revision2,
            mock_revision1,
        ]  # head to current
        mock_script.get_current_head.return_value = "ghi789"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
        ):

            mock_get_config.return_value = Mock()
            mock_get_script.return_value = mock_script
            mock_get_current.return_value = "abc123"

            result = get_pending_revisions(temp_alembic_ini)

            expected = [("def456", "Add user table"), ("ghi789", "Add product table")]
            assert result == expected

    def test_get_pending_revisions_none_pending(self, temp_alembic_ini):
        """Test getting pending revisions when all are applied."""
        mock_script = Mock()
        mock_script.get_current_head.return_value = "abc123"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
        ):

            mock_get_config.return_value = Mock()
            mock_get_script.return_value = mock_script
            mock_get_current.return_value = "abc123"

            result = get_pending_revisions(temp_alembic_ini)
            assert result == []


class TestApplyMigrations:
    """Tests for apply_migrations function."""

    def test_apply_migrations_dry_run(self, temp_alembic_ini, caplog):
        """Test applying migrations in dry-run mode."""
        mock_pending = [("abc123", "Add user table"), ("def456", "Add product table")]

        with (
            patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
        ):

            mock_get_pending.return_value = mock_pending
            mock_get_config.return_value = Mock()

            results = apply_migrations(alembic_ini_path=temp_alembic_ini, dry_run=True)

            assert len(results) == 2
            assert results[0].revision == "abc123"
            assert results[0].action == "pending"
            assert results[1].revision == "def456"
            assert results[1].action == "pending"

            assert "would apply: abc123 - Add user table" in caplog.text

    def test_apply_migrations_success(self, temp_alembic_ini, caplog):
        """Test successful migration application."""
        mock_pending = [("abc123", "Add user table")]

        with (
            patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.upgrade") as mock_upgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", True),
        ):

            mock_get_pending.return_value = mock_pending
            mock_config = Mock()
            mock_get_config.return_value = mock_config

            results = apply_migrations(alembic_ini_path=temp_alembic_ini, dry_run=False)

            assert len(results) == 1
            assert results[0].revision == "abc123"
            assert results[0].action == "applied"
            assert results[0].description == "Add user table"
            assert results[0].duration_seconds is not None

            mock_upgrade.assert_called_once_with(mock_config, "head")

    def test_apply_migrations_success_no_telemetry(self, temp_alembic_ini):
        """Test successful migration application without telemetry."""
        mock_pending = [("abc123", "Add user table")]

        with (
            patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.upgrade") as mock_upgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", False),
        ):

            mock_get_pending.return_value = mock_pending
            mock_config = Mock()
            mock_get_config.return_value = mock_config

            results = apply_migrations(alembic_ini_path=temp_alembic_ini, dry_run=False)

            assert len(results) == 1
            assert results[0].revision == "abc123"
            assert results[0].action == "applied"
            assert results[0].description == "Add user table"
            assert results[0].duration_seconds is not None

            mock_upgrade.assert_called_once_with(mock_config, "head")

    def test_apply_migrations_no_pending(self, temp_alembic_ini, caplog):
        """Test applying migrations when none are pending."""
        with patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending:
            mock_get_pending.return_value = []

            results = apply_migrations(alembic_ini_path=temp_alembic_ini)
            assert results == []

            assert "No pending migrations" in caplog.text

    def test_apply_migrations_failure(self, temp_alembic_ini):
        """Test migration application failure."""
        mock_pending = [("abc123", "Add user table")]

        with (
            patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.upgrade") as mock_upgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", True),
            patch("k0.automation.migrate._migration_status_gauge") as mock_gauge,
        ):

            mock_get_pending.return_value = mock_pending
            mock_upgrade.side_effect = Exception("Migration failed")
            mock_get_config.return_value = Mock()

            with pytest.raises(MigrationError, match="Migration failed"):
                apply_migrations(alembic_ini_path=temp_alembic_ini)

            mock_gauge.set.assert_called_once_with(-1)

    def test_apply_migrations_failure_no_telemetry(self, temp_alembic_ini):
        """Test migration application failure without telemetry."""
        mock_pending = [("abc123", "Add user table")]

        with (
            patch("k0.automation.migrate.get_pending_revisions") as mock_get_pending,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("alembic.command.upgrade") as mock_upgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", False),
        ):

            mock_get_pending.return_value = mock_pending
            mock_upgrade.side_effect = Exception("Migration failed")
            mock_get_config.return_value = Mock()

            with pytest.raises(MigrationError, match="Migration failed"):
                apply_migrations(alembic_ini_path=temp_alembic_ini)


class TestRollbackMigration:
    """Tests for rollback_migration function."""

    def test_rollback_migration_steps(self, temp_alembic_ini, caplog):
        """Test rolling back migrations by steps."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("alembic.command.downgrade") as mock_downgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", True),
            patch("k0.automation.migrate._migration_rollback_counter") as mock_counter,
        ):

            mock_get_current.return_value = "def456"
            mock_config = Mock()
            mock_get_config.return_value = mock_config
            mock_get_script.return_value = mock_script

            # Mock iterate_revisions to return one revision
            mock_script.iterate_revisions.return_value = [mock_revision]

            results = rollback_migration(alembic_ini_path=temp_alembic_ini, steps=1)

            assert len(results) == 1
            assert results[0].revision == "abc123"
            assert results[0].action == "rolled_back"

            mock_downgrade.assert_called_once_with(mock_config, "-1")
            mock_counter.inc.assert_called_once_with(1)

    def test_rollback_migration_steps_no_telemetry(self, temp_alembic_ini):
        """Test rolling back migrations by steps without telemetry."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("alembic.command.downgrade") as mock_downgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", False),
        ):

            mock_get_current.return_value = "def456"
            mock_config = Mock()
            mock_get_config.return_value = mock_config
            mock_get_script.return_value = mock_script

            # Mock iterate_revisions to return one revision
            mock_script.iterate_revisions.return_value = [mock_revision]

            results = rollback_migration(alembic_ini_path=temp_alembic_ini, steps=1)

            assert len(results) == 1
            assert results[0].revision == "abc123"
            assert results[0].action == "rolled_back"

            mock_downgrade.assert_called_once_with(mock_config, "-1")

    def test_rollback_migration_dry_run(self, temp_alembic_ini, caplog):
        """Test rolling back migrations in dry-run mode."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
        ):

            mock_get_current.return_value = "def456"
            mock_get_config.return_value = Mock()
            mock_get_script.return_value = mock_script
            mock_script.iterate_revisions.return_value = [mock_revision]

            results = rollback_migration(alembic_ini_path=temp_alembic_ini, steps=1, dry_run=True)

            assert len(results) == 1
            assert results[0].action == "pending"
            assert "would rollback: abc123" in caplog.text

    def test_rollback_migration_failure(self, temp_alembic_ini):
        """Test rollback migration failure."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("alembic.command.downgrade") as mock_downgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", True),
            patch("k0.automation.migrate._migration_status_gauge") as mock_gauge,
        ):

            mock_get_current.return_value = "def456"
            mock_config = Mock()
            mock_get_config.return_value = mock_config
            mock_get_script.return_value = mock_script
            mock_script.iterate_revisions.return_value = [mock_revision]
            mock_downgrade.side_effect = Exception("Downgrade failed")

            with pytest.raises(MigrationError, match="Rollback failed"):
                rollback_migration(alembic_ini_path=temp_alembic_ini, steps=1)

            mock_gauge.set.assert_called_once_with(-1)

    def test_rollback_migration_target_revision(self, temp_alembic_ini):
        """Test rolling back migrations to specific revision."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "def456"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("alembic.command.downgrade") as mock_downgrade,
            patch("k0.automation.migrate._TELEMETRY_ENABLED", False),
        ):

            mock_get_current.return_value = "ghi789"
            mock_config = Mock()
            mock_get_config.return_value = mock_config
            mock_get_script.return_value = mock_script

            # Mock iterate_revisions to return one revision (from current to target, excluding target)
            mock_script.iterate_revisions.return_value = [mock_revision]

            results = rollback_migration(
                alembic_ini_path=temp_alembic_ini, target_revision="abc123"
            )

            assert len(results) == 1
            assert results[0].revision == "def456"
            assert results[0].action == "rolled_back"

            mock_downgrade.assert_called_once_with(mock_config, "abc123")


class TestGetMigrationHistory:
    """Tests for get_migration_history function."""

    def test_get_migration_history(self, temp_alembic_ini):
        """Test retrieving migration history."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
        ):

            mock_get_config.return_value = Mock()
            mock_get_script.return_value = mock_script
            mock_get_current.return_value = "abc123"

            mock_script.iterate_revisions.return_value = [mock_revision]

            history = get_migration_history(temp_alembic_ini)

            assert len(history) == 1
            assert history[0] == ("abc123", "Add user table", True)

    def test_get_migration_history_no_current(self, temp_alembic_ini):
        """Test retrieving migration history when no migrations applied."""
        mock_script = Mock()
        mock_revision = Mock()
        mock_revision.revision = "abc123"
        mock_revision.doc = "Add user table"

        with (
            patch("k0.automation.migrate._get_alembic_config") as mock_get_config,
            patch("k0.automation.migrate._get_script_directory") as mock_get_script,
            patch("k0.automation.migrate.get_current_revision") as mock_get_current,
        ):

            mock_get_config.return_value = Mock()
            mock_get_script.return_value = mock_script
            mock_get_current.return_value = None

            mock_script.iterate_revisions.return_value = [mock_revision]

            history = get_migration_history(temp_alembic_ini)

            assert len(history) == 1
            assert history[0] == ("abc123", "Add user table", False)
