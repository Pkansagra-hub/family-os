"""
Test suite for Intent Routing Schema Migrations (Phase 1).

Validates Alembic migrations for GAP-001 Intent & Ingress Matrix:
- 0057_st_prospective_intent_types.py - Extend intention_type CHECK
- 0058_st_sem_pattern_types.py - Extend pattern_type CHECK
- 0059_kg_query_tracking.py - Add query tracking columns

Plan Reference: docs/plans/INTENT_INGRESS_MATRIX_IMPLEMENTATION_PLAN.md Phase 1

These tests validate migration structure without requiring a database connection.
For integration testing with real PostgreSQL, run the migrations in a test database.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, List
from unittest.mock import patch

import pytest
import sqlalchemy as sa

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def migrations_path() -> Path:
    """Return the path to Alembic migrations directory."""
    # tests/k0/db/alembic/test_*.py -> 4 parents to get to repo root
    return Path(__file__).parent.parent.parent.parent.parent / "k0" / "db" / "alembic" / "versions"


def load_migration_module(migrations_path: Path, migration_name: str) -> Any:
    """Dynamically load a migration module."""
    migration_file = migrations_path / f"{migration_name}.py"
    if not migration_file.exists():
        pytest.skip(f"Migration {migration_name} not found")

    spec = importlib.util.spec_from_file_location(migration_name, migration_file)
    if spec is None or spec.loader is None:
        pytest.skip(f"Could not load migration {migration_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[migration_name] = module
    spec.loader.exec_module(module)
    return module


class MockOp:
    """Mock for alembic.op to capture migration operations."""

    def __init__(self):
        self.sql_executed: List[str] = []
        self.columns_added: List[dict] = []
        self.columns_dropped: List[dict] = []
        self.indexes_created: List[dict] = []
        self.indexes_dropped: List[dict] = []

    def execute(self, sql: str):
        """Capture raw SQL execution."""
        self.sql_executed.append(sql)

    def add_column(self, table_name: str, column: sa.Column):
        """Capture column addition."""
        self.columns_added.append(
            {
                "table": table_name,
                "column_name": column.name,
                "column_type": type(column.type).__name__,
                "nullable": column.nullable,
                "server_default": column.server_default,
            }
        )

    def drop_column(self, table_name: str, column_name: str):
        """Capture column drop."""
        self.columns_dropped.append(
            {
                "table": table_name,
                "column_name": column_name,
            }
        )

    def create_index(self, name: str, table_name: str, columns: list, **kwargs):
        """Capture index creation."""
        self.indexes_created.append(
            {
                "name": name,
                "table": table_name,
                "columns": columns,
                "kwargs": kwargs,
            }
        )

    def drop_index(self, name: str, table_name: str | None = None, **kwargs):
        """Capture index drop."""
        self.indexes_dropped.append(
            {
                "name": name,
                "table": table_name,
                "kwargs": kwargs,
            }
        )


# =============================================================================
# TEST 0057: st_prospective intention_type CHECK extension
# =============================================================================


class TestMigration0057StProspectiveIntentTypes:
    """Test suite for st_prospective intention_type CHECK extension."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0057_st_prospective_intent_types migration module."""
        return load_migration_module(migrations_path, "0057_st_prospective_intent_types")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0057"
        assert migration_module.down_revision == "0056"

    def test_upgrade_drops_old_constraint(self, migration_module, mock_op):
        """Verify upgrade() drops old ck_prosp_intention_type constraint."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check DROP CONSTRAINT was executed
        drop_statements = [
            sql
            for sql in mock_op.sql_executed
            if "DROP CONSTRAINT" in sql and "ck_prosp_intention_type" in sql
        ]
        assert len(drop_statements) == 1

    def test_upgrade_adds_extended_constraint(self, migration_module, mock_op):
        """Verify upgrade() adds extended CHECK constraint with DECISION, COUNTERFACTUAL."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Check ADD CONSTRAINT was executed with new values
        add_statements = [
            sql
            for sql in mock_op.sql_executed
            if "ADD CONSTRAINT" in sql and "ck_prosp_intention_type" in sql
        ]
        assert len(add_statements) == 1

        # Verify new values are in the constraint
        constraint_sql = add_statements[0]
        assert "DECISION" in constraint_sql
        assert "COUNTERFACTUAL" in constraint_sql

        # Verify original values are preserved
        assert "GOAL" in constraint_sql
        assert "PLAN" in constraint_sql
        assert "REMINDER" in constraint_sql
        assert "COMMITMENT" in constraint_sql
        assert "WISH" in constraint_sql

    def test_downgrade_restores_original_constraint(self, migration_module, mock_op):
        """Verify downgrade() restores original CHECK constraint."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Check DROP and ADD were executed
        drop_statements = [sql for sql in mock_op.sql_executed if "DROP CONSTRAINT" in sql]
        add_statements = [sql for sql in mock_op.sql_executed if "ADD CONSTRAINT" in sql]

        assert len(drop_statements) == 1
        assert len(add_statements) == 1

        # Verify new values are NOT in the restored constraint
        constraint_sql = add_statements[0]
        assert "DECISION" not in constraint_sql
        assert "COUNTERFACTUAL" not in constraint_sql

    def test_upgrade_idempotent_drop(self, migration_module, mock_op):
        """Verify DROP uses IF EXISTS for idempotency."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        drop_statements = [sql for sql in mock_op.sql_executed if "DROP CONSTRAINT" in sql]
        assert any("IF EXISTS" in sql for sql in drop_statements)


# =============================================================================
# TEST 0058: st_sem pattern_type CHECK extension
# =============================================================================


class TestMigration0058StSemPatternTypes:
    """Test suite for st_sem pattern_type CHECK extension."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0058_st_sem_pattern_types migration module."""
        return load_migration_module(migrations_path, "0058_st_sem_pattern_types")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0058"
        assert migration_module.down_revision == "0057"

    def test_upgrade_drops_old_constraint(self, migration_module, mock_op):
        """Verify upgrade() drops old ck_sem_pattern_type constraint."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        drop_statements = [
            sql
            for sql in mock_op.sql_executed
            if "DROP CONSTRAINT" in sql and "ck_sem_pattern_type" in sql
        ]
        assert len(drop_statements) == 1

    def test_upgrade_adds_extended_constraint(self, migration_module, mock_op):
        """Verify upgrade() adds extended CHECK constraint with LESSON, EMOTIONAL_TREND, INSIGHT."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        add_statements = [
            sql
            for sql in mock_op.sql_executed
            if "ADD CONSTRAINT" in sql and "ck_sem_pattern_type" in sql
        ]
        assert len(add_statements) == 1

        # Verify new values are in the constraint
        constraint_sql = add_statements[0]
        assert "LESSON" in constraint_sql
        assert "EMOTIONAL_TREND" in constraint_sql
        assert "INSIGHT" in constraint_sql

        # Verify original values are preserved
        assert "ROUTINE" in constraint_sql
        assert "PREFERENCE" in constraint_sql
        assert "THEME" in constraint_sql
        assert "RELATIONSHIP" in constraint_sql
        assert "GOAL" in constraint_sql
        assert "VALUE" in constraint_sql

    def test_downgrade_restores_original_constraint(self, migration_module, mock_op):
        """Verify downgrade() restores original CHECK constraint."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        add_statements = [sql for sql in mock_op.sql_executed if "ADD CONSTRAINT" in sql]

        assert len(add_statements) == 1

        # Verify new values are NOT in the restored constraint
        constraint_sql = add_statements[0]
        assert "LESSON" not in constraint_sql
        assert "EMOTIONAL_TREND" not in constraint_sql
        assert "INSIGHT" not in constraint_sql


# =============================================================================
# TEST 0059: KG Query Tracking columns
# =============================================================================


class TestMigration0059KgQueryTracking:
    """Test suite for st_kg_dom and st_kg_edges query tracking columns."""

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the 0059_kg_query_tracking migration module."""
        return load_migration_module(migrations_path, "0059_kg_query_tracking")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision identifiers."""
        assert migration_module.revision == "0059"
        assert migration_module.down_revision == "0058"

    def test_upgrade_adds_st_kg_dom_columns(self, migration_module, mock_op):
        """Verify upgrade() adds query_count, last_queried_at, milestones_json to st_kg_dom."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Filter for st_kg_dom columns
        kg_dom_columns = [col for col in mock_op.columns_added if col["table"] == "st_kg_dom"]

        # Verify 3 columns added
        assert len(kg_dom_columns) == 3

        # Verify column names
        col_names = {col["column_name"] for col in kg_dom_columns}
        assert "query_count" in col_names
        assert "last_queried_at" in col_names
        assert "milestones_json" in col_names

        # Verify query_count has default 0
        query_count_col = next(col for col in kg_dom_columns if col["column_name"] == "query_count")
        assert query_count_col["column_type"] == "Integer"
        assert query_count_col["server_default"] is not None

    def test_upgrade_adds_st_kg_edges_columns(self, migration_module, mock_op):
        """Verify upgrade() adds query_count, last_queried_at, sentiment_avg to st_kg_edges."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Filter for st_kg_edges columns
        kg_edges_columns = [col for col in mock_op.columns_added if col["table"] == "st_kg_edges"]

        # Verify 3 columns added
        assert len(kg_edges_columns) == 3

        # Verify column names
        col_names = {col["column_name"] for col in kg_edges_columns}
        assert "query_count" in col_names
        assert "last_queried_at" in col_names
        assert "sentiment_avg" in col_names

        # Verify sentiment_avg is Float
        sentiment_col = next(
            col for col in kg_edges_columns if col["column_name"] == "sentiment_avg"
        )
        assert sentiment_col["column_type"] == "Float"

    def test_upgrade_creates_indexes(self, migration_module, mock_op):
        """Verify upgrade() creates indexes for query_count columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        # Verify 2 indexes created
        assert len(mock_op.indexes_created) == 2

        index_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "idx_kg_dom_query_count" in index_names
        assert "idx_kg_edges_query_count" in index_names

    def test_downgrade_drops_columns(self, migration_module, mock_op):
        """Verify downgrade() drops all added columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Verify 6 columns dropped (3 per table)
        assert len(mock_op.columns_dropped) == 6

        # Verify correct tables
        tables = {col["table"] for col in mock_op.columns_dropped}
        assert "st_kg_dom" in tables
        assert "st_kg_edges" in tables

        # Verify correct column names
        col_names = {col["column_name"] for col in mock_op.columns_dropped}
        assert "query_count" in col_names
        assert "last_queried_at" in col_names
        assert "milestones_json" in col_names
        assert "sentiment_avg" in col_names

    def test_downgrade_drops_indexes(self, migration_module, mock_op):
        """Verify downgrade() drops indexes before columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        # Verify 2 indexes dropped
        assert len(mock_op.indexes_dropped) == 2

        index_names = {idx["name"] for idx in mock_op.indexes_dropped}
        assert "idx_kg_dom_query_count" in index_names
        assert "idx_kg_edges_query_count" in index_names


# =============================================================================
# INTEGRATION TEST: Migration Chain
# =============================================================================


class TestMigrationChain:
    """Test the migration chain order is correct."""

    @pytest.fixture
    def migrations_path(self) -> Path:
        """Return the path to Alembic migrations directory."""
        return (
            Path(__file__).parent.parent.parent.parent.parent / "k0" / "db" / "alembic" / "versions"
        )

    def test_migration_chain_order(self, migrations_path):
        """Verify migrations 0057 -> 0058 -> 0059 form correct chain."""
        m57 = load_migration_module(migrations_path, "0057_st_prospective_intent_types")
        m58 = load_migration_module(migrations_path, "0058_st_sem_pattern_types")
        m59 = load_migration_module(migrations_path, "0059_kg_query_tracking")

        # Verify chain
        assert m57.revision == "0057"
        assert m57.down_revision == "0056"

        assert m58.revision == "0058"
        assert m58.down_revision == "0057"

        assert m59.revision == "0059"
        assert m59.down_revision == "0058"

    def test_all_migrations_have_upgrade_and_downgrade(self, migrations_path):
        """Verify all migrations have both upgrade() and downgrade() functions."""
        for migration_name in [
            "0057_st_prospective_intent_types",
            "0058_st_sem_pattern_types",
            "0059_kg_query_tracking",
        ]:
            module = load_migration_module(migrations_path, migration_name)

            assert hasattr(module, "upgrade"), f"{migration_name} missing upgrade()"
            assert hasattr(module, "downgrade"), f"{migration_name} missing downgrade()"
            assert callable(module.upgrade), f"{migration_name}.upgrade is not callable"
            assert callable(module.downgrade), f"{migration_name}.downgrade is not callable"
