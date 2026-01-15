"""Tests for migrate_neo4j module.

Tests cover:
- Neo4j migration result dataclass
- Cypher migration application (dry-run and actual)
- Migration file discovery and checksum calculation
- SchemaVersion constraint management
- Applied migration tracking
- Cypher statement splitting
- Error handling for missing migrations and connection failures
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from k0.automation.migrate_neo4j import (
    Neo4jMigrationError,
    Neo4jMigrationResult,
    _ensure_schema_version_constraint,
    _load_applied_migrations,
    _split_cypher_statements,
    apply_cypher_migrations,
)


@pytest.fixture
def temp_migrations_dir():
    """Create temporary migrations directory with sample Cypher files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        migrations_dir = Path(tmpdir) / "migrations"
        migrations_dir.mkdir()

        # Create sample migration files
        migration1 = migrations_dir / "0001_baseline.cypher"
        migration1.write_text(
            """
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;

// Add some initial data
CREATE (:SchemaVersion {version: '0001', checksum: 'test'});
"""
        )

        migration2 = migrations_dir / "0002_add_indexes.cypher"
        migration2.write_text(
            """
CREATE INDEX user_email_index IF NOT EXISTS
FOR (u:User) ON (u.email);

CREATE INDEX post_created_index IF NOT EXISTS
FOR (p:Post) ON (p.created_at);
"""
        )

        yield migrations_dir


class TestNeo4jMigrationResult:
    """Tests for Neo4jMigrationResult dataclass."""

    def test_migration_result_creation(self):
        """Test creating a Neo4jMigrationResult instance."""
        result = Neo4jMigrationResult(
            version="0001_baseline",
            action="applied",
            checksum="abc123",
            path=Path("/tmp/migration.cypher"),
            duration_seconds=2.5,
        )

        assert result.version == "0001_baseline"
        assert result.action == "applied"
        assert result.checksum == "abc123"
        assert result.path == Path("/tmp/migration.cypher")
        assert result.duration_seconds == 2.5

    def test_migration_result_optional_duration(self):
        """Test Neo4jMigrationResult with None duration."""
        result = Neo4jMigrationResult(
            version="0002_indexes",
            action="skipped",
            checksum="def456",
            path=Path("/tmp/migration.cypher"),
        )

        assert result.version == "0002_indexes"
        assert result.action == "skipped"
        assert result.duration_seconds is None


class TestSplitCypherStatements:
    """Tests for _split_cypher_statements function."""

    def test_split_simple_statements(self):
        """Test splitting simple Cypher statements."""
        script = """
CREATE (n:Test);
MATCH (n) RETURN n;
CREATE INDEX test_index FOR (n:Test) ON (n.id);
"""
        statements = _split_cypher_statements(script)
        expected = [
            "CREATE (n:Test)",
            "MATCH (n) RETURN n",
            "CREATE INDEX test_index FOR (n:Test) ON (n.id)",
        ]
        assert statements == expected

    def test_split_with_comments(self):
        """Test splitting statements with comments."""
        script = """
// This is a comment
CREATE (n:Test);
// Another comment
MATCH (n) RETURN n;
"""
        statements = _split_cypher_statements(script)
        expected = ["CREATE (n:Test)", "MATCH (n) RETURN n"]
        assert statements == expected

    def test_split_multiline_statement(self):
        """Test splitting multiline statements."""
        script = """
CREATE (n:Test {
  name: 'test',
  value: 123
});
"""
        statements = _split_cypher_statements(script)
        assert len(statements) == 1
        assert "CREATE (n:Test {" in statements[0]

    def test_split_empty_script(self):
        """Test splitting empty script."""
        statements = _split_cypher_statements("")
        assert statements == []

    def test_split_whitespace_only(self):
        """Test splitting whitespace-only script."""
        statements = _split_cypher_statements("   \n  \n  ")
        assert statements == []


class TestEnsureSchemaVersionConstraint:
    """Tests for _ensure_schema_version_constraint function."""

    def test_constraint_already_exists(self):
        """Test when constraint already exists."""
        mock_session = Mock()
        mock_result = Mock()
        mock_record = Mock()
        mock_record.__getitem__ = Mock(return_value="schema_version_unique")
        mock_result.__iter__ = Mock(return_value=iter([mock_record]))
        mock_session.run.return_value = mock_result

        _ensure_schema_version_constraint(mock_session)

        # Should not create constraint
        assert mock_session.run.call_count == 1
        call_args = mock_session.run.call_args[0][0]
        assert "SHOW CONSTRAINTS" in call_args

    def test_constraint_created(self):
        """Test creating constraint when it doesn't exist."""
        mock_session = Mock()
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))  # No constraints
        mock_session.run.return_value = mock_result

        _ensure_schema_version_constraint(mock_session)

        # Should create constraint
        assert mock_session.run.call_count == 2
        calls = [call[0][0] for call in mock_session.run.call_args_list]
        assert "SHOW CONSTRAINTS" in calls[0]
        assert "CREATE CONSTRAINT schema_version_unique" in calls[1]


class TestLoadAppliedMigrations:
    """Tests for _load_applied_migrations function."""

    def test_load_applied_migrations(self):
        """Test loading applied migrations from database."""
        mock_session = Mock()
        mock_result = Mock()
        mock_record1 = Mock()
        mock_record1.__getitem__ = Mock(
            side_effect=lambda key: {
                "version": "0001",
                "checksum": "abc123",
            }[key]
        )
        mock_record2 = Mock()
        mock_record2.__getitem__ = Mock(
            side_effect=lambda key: {
                "version": "0002",
                "checksum": "def456",
            }[key]
        )
        mock_result.__iter__ = Mock(return_value=iter([mock_record1, mock_record2]))
        mock_session.run.return_value = mock_result

        applied = _load_applied_migrations(mock_session)

        expected = {"0001": "abc123", "0002": "def456"}
        assert applied == expected

    def test_load_no_applied_migrations(self):
        """Test loading when no migrations are applied."""
        mock_session = Mock()
        mock_result = Mock()
        mock_result.__iter__ = Mock(return_value=iter([]))
        mock_session.run.return_value = mock_result

        applied = _load_applied_migrations(mock_session)

        assert applied == {}


class TestApplyCypherMigrations:
    """Tests for apply_cypher_migrations function."""

    def test_apply_migrations_dry_run(self, temp_migrations_dir, caplog):
        """Test applying migrations in dry-run mode."""
        with (
            patch("neo4j.GraphDatabase") as mock_graph_db,
            patch("k0.automation.migrate_neo4j._load_applied_migrations") as mock_load,
        ):
            mock_driver = Mock()
            mock_session = Mock()
            mock_graph_db.driver.return_value = mock_driver
            mock_session_cm = Mock()
            mock_session_cm.__enter__ = Mock(return_value=mock_session)
            mock_session_cm.__exit__ = Mock(return_value=None)
            mock_driver.session.return_value = mock_session_cm
            mock_load.return_value = {}

            # Mock constraint check
            mock_constraint_result = Mock()
            mock_constraint_result.__iter__ = Mock(return_value=iter([]))
            mock_session.run.side_effect = [mock_constraint_result, Mock(), Mock()]

            results = apply_cypher_migrations(
                uri="neo4j://localhost:7687",
                username="neo4j",
                password="password",
                migrations_path=temp_migrations_dir,
                dry_run=True,
            )

            assert len(results) == 2
            assert results[0].action == "pending"
            assert results[1].action == "pending"
            assert "would apply migration 0001_baseline" in caplog.text

    def test_apply_migrations_success(self, temp_migrations_dir):
        """Test successful migration application."""
        with (
            patch("neo4j.GraphDatabase") as mock_graph_db,
            patch("k0.automation.migrate_neo4j._load_applied_migrations") as mock_load,
            patch("k0.automation.migrate_neo4j._TELEMETRY_ENABLED", True),
        ):

            mock_driver = Mock()
            mock_session = Mock()
            mock_graph_db.driver.return_value = mock_driver
            mock_session_cm = Mock()
            mock_session_cm.__enter__ = Mock(return_value=mock_session)
            mock_session_cm.__exit__ = Mock(return_value=None)
            mock_driver.session.return_value = mock_session_cm
            mock_load.return_value = {}  # No applied migrations

            # Mock constraint check and migration operations
            mock_constraint_result = Mock()
            mock_constraint_result.__iter__ = Mock(return_value=iter([]))
            mock_session.run.side_effect = [
                mock_constraint_result,  # SHOW CONSTRAINTS
                Mock(),  # CREATE CONSTRAINT
                Mock(),  # First migration DDL
                Mock(),  # First migration DML
                Mock(),  # Second migration DDL
                Mock(),  # Second migration DML
            ]

            results = apply_cypher_migrations(
                uri="neo4j://localhost:7687",
                username="neo4j",
                password="password",
                migrations_path=temp_migrations_dir,
                dry_run=False,
            )

            assert len(results) == 2
            assert results[0].action == "applied"
            assert results[1].action == "applied"
            assert results[0].version == "0001_baseline"
            assert results[1].version == "0002_add_indexes"

    def test_apply_migrations_already_applied(self, temp_migrations_dir):
        """Test when migrations are already applied."""
        with (
            patch("neo4j.GraphDatabase") as mock_graph_db,
            patch("k0.automation.migrate_neo4j._load_applied_migrations") as mock_load,
        ):

            mock_driver = Mock()
            mock_session = Mock()
            mock_graph_db.driver.return_value = mock_driver
            mock_session_cm = Mock()
            mock_session_cm.__enter__ = Mock(return_value=mock_session)
            mock_session_cm.__exit__ = Mock(return_value=None)
            mock_driver.session.return_value = mock_session_cm

            # Mock all migrations as applied
            mock_load.return_value = {
                "0001_baseline": "09e89c9a91516a68b78052e54ace2210d84f9b39ead1675a3b07d78d516e8291",
                "0002_add_indexes": "ea3bb08c51c7ba651fc39fbe5bad5688788f53d903767d4329c060497952241d",
            }

            # Mock constraint check
            mock_constraint_result = Mock()
            mock_constraint_result.__iter__ = Mock(return_value=iter([]))
            mock_session.run.return_value = mock_constraint_result

            results = apply_cypher_migrations(
                uri="neo4j://localhost:7687",
                username="neo4j",
                password="password",
                migrations_path=temp_migrations_dir,
            )

            assert len(results) == 2
            assert all(r.action == "skipped" for r in results)

    def test_apply_migrations_checksum_mismatch(self, temp_migrations_dir):
        """Test checksum mismatch detection."""
        with (
            patch("neo4j.GraphDatabase") as mock_graph_db,
            patch("k0.automation.migrate_neo4j._load_applied_migrations") as mock_load,
        ):

            mock_driver = Mock()
            mock_session = Mock()
            mock_graph_db.driver.return_value = mock_driver
            mock_session_cm = Mock()
            mock_session_cm.__enter__ = Mock(return_value=mock_session)
            mock_session_cm.__exit__ = Mock(return_value=None)
            mock_driver.session.return_value = mock_session_cm

            # Mock mismatch checksum
            mock_load.return_value = {"0001_baseline": "wrong_checksum"}

            # Mock constraint check
            mock_constraint_result = Mock()
            mock_constraint_result.__iter__ = Mock(return_value=iter([]))
            mock_session.run.return_value = mock_constraint_result

            with pytest.raises(Neo4jMigrationError, match="Checksum mismatch"):
                apply_cypher_migrations(
                    uri="neo4j://localhost:7687",
                    username="neo4j",
                    password="password",
                    migrations_path=temp_migrations_dir,
                )

    def test_apply_migrations_no_directory(self):
        """Test when migrations directory doesn't exist."""
        with pytest.raises(Neo4jMigrationError, match="Migration directory does not exist"):
            apply_cypher_migrations(
                uri="neo4j://localhost:7687",
                username="neo4j",
                password="password",
                migrations_path=Path("C:/definitely/does/not/exist"),
            )

    def test_apply_migrations_no_files(self):
        """Test when migrations directory is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_dir = Path(tmpdir)

            with pytest.raises(Neo4jMigrationError, match="No migration files found"):
                apply_cypher_migrations(
                    uri="neo4j://localhost:7687",
                    username="neo4j",
                    password="password",
                    migrations_path=empty_dir,
                )

    def test_apply_migrations_neo4j_not_installed(self):
        """Test when neo4j driver is not installed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations_dir = Path(tmpdir)
            (migrations_dir / "test.cypher").write_text("CREATE (n:Test);")

            with patch.dict("sys.modules", {"neo4j": None}):
                with pytest.raises(Neo4jMigrationError, match="neo4j driver not installed"):
                    apply_cypher_migrations(
                        uri="neo4j://localhost:7687",
                        username="neo4j",
                        password="password",
                        migrations_path=migrations_dir,
                    )
