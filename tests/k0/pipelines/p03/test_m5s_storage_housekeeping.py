"""
Test suite for M5.S Storage Housekeeping migrations.

Validates:
- 5.S.1.2: Migration 0075 - composite index (status, entity_id) on st_learning_queue
- 5.S.1.5: Migration 0048 - merge_cascade_id indexes on 7 cascade tables

These tests validate migration structure without requiring a database connection.
Follows the MockOp pattern from test_p03_storage_migrations.py.

Plan Reference: PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md, Milestone 5 (M5.S)
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import sqlalchemy as sa

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def migrations_path() -> Path:
    """Return the path to Alembic migrations directory."""
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
        self.tables_created: List[Dict[str, Any]] = []
        self.tables_dropped: List[str] = []
        self.indexes_created: List[Dict[str, Any]] = []
        self.indexes_dropped: List[Dict[str, Any]] = []
        self.columns_added: List[Dict[str, Any]] = []
        self.columns_dropped: List[Dict[str, Any]] = []
        self.constraints_added: List[Dict[str, Any]] = []
        self.constraints_dropped: List[Dict[str, Any]] = []
        self.sql_executed: List[str] = []

    def create_table(self, name: str, *columns, **kwargs):
        """Capture table creation."""
        col_info = []
        constraints = []
        for col in columns:
            if isinstance(col, sa.Column):
                col_info.append(
                    {
                        "name": col.name,
                        "type": type(col.type).__name__,
                        "nullable": col.nullable,
                        "primary_key": col.primary_key,
                        "index": getattr(col, "index", None),
                    }
                )
            elif isinstance(col, sa.CheckConstraint):
                constraints.append(
                    {
                        "type": "check",
                        "name": col.name,
                        "sqltext": str(col.sqltext) if hasattr(col, "sqltext") else None,
                    }
                )
        self.tables_created.append(
            {
                "name": name,
                "columns": col_info,
                "constraints": constraints,
                "kwargs": kwargs,
            }
        )

    def drop_table(self, name: str):
        """Capture table drop."""
        self.tables_dropped.append(name)

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

    def drop_index(self, name: str, table_name: str = None, **kwargs):
        """Capture index drop."""
        self.indexes_dropped.append(
            {
                "name": name,
                "table": table_name,
                "kwargs": kwargs,
            }
        )

    def add_column(self, table_name: str, column: sa.Column):
        """Capture column addition."""
        self.columns_added.append(
            {
                "table": table_name,
                "column_name": column.name,
                "column_type": type(column.type).__name__,
                "nullable": column.nullable,
                "index": getattr(column, "index", None),
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

    def execute(self, sql: str):
        """Capture raw SQL execution."""
        self.sql_executed.append(sql)


# =============================================================================
# 5.S.1.2: Migration 0075 - Composite index (status, entity_id)
# =============================================================================


class TestMigration0075StLearningQueueStatusEntityIdx:
    """Test suite for migration 0075_st_learning_queue_status_entity_idx.py.

    Validates the composite index addition for R4 Discovery SG-003
    entity-scoped gap lookups by status.

    Plan: Issue 5.S.1.2
    AC: Migration added; query plan uses index
    """

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the migration module."""
        return load_migration_module(migrations_path, "0075_st_learning_queue_status_entity_idx")

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision chain."""
        assert migration_module.revision == "0075"
        assert migration_module.down_revision == "0074"

    def test_branch_labels_none(self, migration_module):
        """Verify no branch labels (linear migration chain)."""
        assert migration_module.branch_labels is None

    def test_depends_on_none(self, migration_module):
        """Verify no external dependencies."""
        assert migration_module.depends_on is None

    def test_upgrade_creates_composite_index(self, migration_module, mock_op):
        """Verify upgrade() creates idx_learning_queue_status_entity."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 1
        idx = mock_op.indexes_created[0]
        assert idx["name"] == "idx_learning_queue_status_entity"
        assert idx["table"] == "st_learning_queue"
        assert idx["columns"] == ["status", "entity_id"]

    def test_upgrade_index_is_not_partial(self, migration_module, mock_op):
        """Verify the index is not partial (covers all statuses)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx = mock_op.indexes_created[0]
        assert "postgresql_where" not in idx.get("kwargs", {})

    def test_upgrade_index_is_not_unique(self, migration_module, mock_op):
        """Verify the index is not unique (multiple gaps per entity allowed)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx = mock_op.indexes_created[0]
        assert idx.get("kwargs", {}).get("unique") is not True

    def test_upgrade_no_table_changes(self, migration_module, mock_op):
        """Verify upgrade() only creates index, no table/column changes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.tables_created) == 0
        assert len(mock_op.columns_added) == 0

    def test_downgrade_drops_index(self, migration_module, mock_op):
        """Verify downgrade() drops the composite index."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert len(mock_op.indexes_dropped) == 1
        dropped = mock_op.indexes_dropped[0]
        assert dropped["name"] == "idx_learning_queue_status_entity"
        assert dropped["table"] == "st_learning_queue"

    def test_downgrade_no_table_changes(self, migration_module, mock_op):
        """Verify downgrade() only drops index, no table/column changes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert len(mock_op.tables_dropped) == 0
        assert len(mock_op.columns_dropped) == 0

    def test_upgrade_downgrade_symmetry(self, migration_module, mock_op):
        """Verify upgrade() and downgrade() are symmetric."""
        mock_op_up = MockOp()
        mock_op_down = MockOp()

        with patch.object(migration_module, "op", mock_op_up):
            migration_module.upgrade()
        with patch.object(migration_module, "op", mock_op_down):
            migration_module.downgrade()

        # Same index name created and dropped
        assert mock_op_up.indexes_created[0]["name"] == mock_op_down.indexes_dropped[0]["name"]

    def test_index_column_order_status_first(self, migration_module, mock_op):
        """Verify status column is first (most selective for filtered queries)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx = mock_op.indexes_created[0]
        assert idx["columns"][0] == "status"
        assert idx["columns"][1] == "entity_id"

    def test_migration_file_exists(self, migrations_path: Path):
        """Verify migration file is present in alembic versions directory."""
        migration_file = migrations_path / "0075_st_learning_queue_status_entity_idx.py"
        assert migration_file.exists(), "Migration 0075 file not found"

    def test_migration_source_references_r4_discovery(self, migration_module):
        """Verify migration docstring references R4 Discovery SG-003."""
        source = inspect.getsource(migration_module)
        assert "R4 Discovery" in source or "SG-003" in source


# =============================================================================
# 5.S.1.5: Migration 0048 - merge_cascade_id indexes verification
# =============================================================================


class TestMigration0048MergeCascadeIndexes:
    """Test suite for migration 0048_st_entity_merges.py cascade index verification.

    Validates that merge_cascade_id is added with index=True to all 7
    cascade tables, and that composite indexes exist on st_entity_merges.

    Plan: Issue 5.S.1.5
    AC: Migration added; merge_cascade_id indexes verified
    """

    CASCADE_TABLES = [
        "st_kg_edges",
        "st_hipp_events",
        "st_epi",
        "st_sem",
        "st_social",
        "st_procedural",
        "st_vec",
    ]

    @pytest.fixture
    def mock_op(self) -> MockOp:
        """Create mock operation tracker."""
        return MockOp()

    @pytest.fixture
    def migration_module(self, migrations_path: Path) -> Any:
        """Load the migration module."""
        return load_migration_module(migrations_path, "0048_st_entity_merges")

    # -- Revision chain --

    def test_revision_identifiers(self, migration_module):
        """Verify migration has correct revision chain."""
        assert migration_module.revision == "0048"
        assert migration_module.down_revision == "0047"

    # -- st_entity_merges table --

    def test_upgrade_creates_entity_merges_table(self, migration_module, mock_op):
        """Verify upgrade() creates st_entity_merges table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        table_names = [t["name"] for t in mock_op.tables_created]
        assert "st_entity_merges" in table_names

    def test_entity_merges_required_columns(self, migration_module, mock_op):
        """Verify st_entity_merges has all required columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        merges_table = next(t for t in mock_op.tables_created if t["name"] == "st_entity_merges")
        col_names = {c["name"] for c in merges_table["columns"]}

        required = {
            "merge_id",
            "tenant_id",
            "space_id",
            "primary_entity_id",
            "secondary_entity_id",
            "primary_snapshot",
            "secondary_snapshot",
            "cascade_counts",
            "merge_reason",
            "initiated_by",
            "merged_at",
            "reversed_at",
            "reversed_by",
            "schema_version",
        }
        missing = required - col_names
        assert not missing, f"Missing columns in st_entity_merges: {missing}"

    def test_entity_merges_primary_key(self, migration_module, mock_op):
        """Verify merge_id is the primary key."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        merges_table = next(t for t in mock_op.tables_created if t["name"] == "st_entity_merges")
        pk_cols = [c for c in merges_table["columns"] if c.get("primary_key")]
        assert len(pk_cols) == 1
        assert pk_cols[0]["name"] == "merge_id"

    # -- merge_cascade_id on 7 cascade tables --

    def test_cascade_tables_get_merge_cascade_id(self, migration_module, mock_op):
        """Verify merge_cascade_id is added to all 7 cascade tables."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        tables_with_cascade = {
            col["table"]
            for col in mock_op.columns_added
            if col["column_name"] == "merge_cascade_id"
        }
        expected = set(self.CASCADE_TABLES)
        missing = expected - tables_with_cascade
        assert not missing, f"Missing merge_cascade_id on tables: {missing}"

    @pytest.mark.parametrize(
        "table_name",
        [
            "st_kg_edges",
            "st_hipp_events",
            "st_epi",
            "st_sem",
            "st_social",
            "st_procedural",
            "st_vec",
        ],
    )
    def test_merge_cascade_id_nullable(self, migration_module, mock_op, table_name):
        """Verify merge_cascade_id is nullable (NULL = not from a merge)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col = next(
            c
            for c in mock_op.columns_added
            if c["table"] == table_name and c["column_name"] == "merge_cascade_id"
        )
        assert col["nullable"] is True

    @pytest.mark.parametrize(
        "table_name",
        [
            "st_kg_edges",
            "st_hipp_events",
            "st_epi",
            "st_sem",
            "st_social",
            "st_procedural",
            "st_vec",
        ],
    )
    def test_merge_cascade_id_has_index(self, migration_module, mock_op, table_name):
        """Verify merge_cascade_id has index=True for targeted undo lookups."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        col = next(
            c
            for c in mock_op.columns_added
            if c["table"] == table_name and c["column_name"] == "merge_cascade_id"
        )
        assert col["index"] is True, f"merge_cascade_id on {table_name} missing index=True"

    def test_merge_cascade_id_column_type(self, migration_module, mock_op):
        """Verify merge_cascade_id is String(36) (UUID format)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        for col in mock_op.columns_added:
            if col["column_name"] == "merge_cascade_id":
                assert col["column_type"] in ("String", "VARCHAR"), (
                    f"Expected String type for merge_cascade_id on {col['table']}, "
                    f"got {col['column_type']}"
                )

    # -- st_kg_dom merge columns --

    def test_kg_dom_gets_merge_columns(self, migration_module, mock_op):
        """Verify st_kg_dom gets merged_into, merged_at, merged_by columns."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        kg_dom_cols = {c["column_name"] for c in mock_op.columns_added if c["table"] == "st_kg_dom"}
        required = {"merged_into", "merged_at", "merged_by"}
        missing = required - kg_dom_cols
        assert not missing, f"Missing merge columns on st_kg_dom: {missing}"

    def test_kg_dom_merged_into_has_index(self, migration_module, mock_op):
        """Verify merged_into on st_kg_dom has index for reverse lookups."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        merged_into_col = next(
            c
            for c in mock_op.columns_added
            if c["table"] == "st_kg_dom" and c["column_name"] == "merged_into"
        )
        assert merged_into_col["index"] is True

    # -- Composite indexes on st_entity_merges --

    def test_composite_index_entity_lookup(self, migration_module, mock_op):
        """Verify composite index for entity lookup queries."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "ix_st_entity_merges_entity_lookup" in idx_names

        entity_idx = next(
            i for i in mock_op.indexes_created if i["name"] == "ix_st_entity_merges_entity_lookup"
        )
        assert entity_idx["columns"] == ["primary_entity_id", "secondary_entity_id"]

    def test_composite_index_active_merges(self, migration_module, mock_op):
        """Verify partial index for active (non-reversed) merges."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "ix_st_entity_merges_active" in idx_names

        active_idx = next(
            i for i in mock_op.indexes_created if i["name"] == "ix_st_entity_merges_active"
        )
        assert "postgresql_where" in active_idx.get("kwargs", {})

    def test_composite_index_reversed_merges(self, migration_module, mock_op):
        """Verify partial index for reversed merges (audit trail)."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        idx_names = {idx["name"] for idx in mock_op.indexes_created}
        assert "ix_st_entity_merges_reversed" in idx_names

        reversed_idx = next(
            i for i in mock_op.indexes_created if i["name"] == "ix_st_entity_merges_reversed"
        )
        assert "postgresql_where" in reversed_idx.get("kwargs", {})

    def test_total_composite_indexes(self, migration_module, mock_op):
        """Verify exactly 3 composite indexes are created on st_entity_merges."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.upgrade()

        assert len(mock_op.indexes_created) == 3

    # -- Downgrade symmetry --

    def test_downgrade_drops_all_cascade_columns(self, migration_module, mock_op):
        """Verify downgrade() removes merge_cascade_id from all 7 tables."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        dropped_tables = {
            c["table"] for c in mock_op.columns_dropped if c["column_name"] == "merge_cascade_id"
        }
        expected = set(self.CASCADE_TABLES)
        missing = expected - dropped_tables
        assert not missing, f"Downgrade missed dropping merge_cascade_id from: {missing}"

    def test_downgrade_drops_kg_dom_columns(self, migration_module, mock_op):
        """Verify downgrade() removes merge columns from st_kg_dom."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        kg_dom_dropped = {
            c["column_name"] for c in mock_op.columns_dropped if c["table"] == "st_kg_dom"
        }
        required = {"merged_into", "merged_at", "merged_by"}
        assert required.issubset(kg_dom_dropped)

    def test_downgrade_drops_table(self, migration_module, mock_op):
        """Verify downgrade() drops st_entity_merges table."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert "st_entity_merges" in mock_op.tables_dropped

    def test_downgrade_drops_composite_indexes(self, migration_module, mock_op):
        """Verify downgrade() drops all 3 composite indexes."""
        with patch.object(migration_module, "op", mock_op):
            migration_module.downgrade()

        assert len(mock_op.indexes_dropped) == 3
        dropped_names = {idx["name"] for idx in mock_op.indexes_dropped}
        expected = {
            "ix_st_entity_merges_entity_lookup",
            "ix_st_entity_merges_active",
            "ix_st_entity_merges_reversed",
        }
        assert expected == dropped_names

    def test_upgrade_downgrade_round_trip(self, migration_module):
        """Verify upgrade followed by downgrade is clean."""
        mock_up = MockOp()
        mock_down = MockOp()

        with patch.object(migration_module, "op", mock_up):
            migration_module.upgrade()
        with patch.object(migration_module, "op", mock_down):
            migration_module.downgrade()

        # Every created index should have a corresponding drop
        up_index_names = {i["name"] for i in mock_up.indexes_created}
        down_index_names = {i["name"] for i in mock_down.indexes_dropped}
        assert up_index_names == down_index_names

        # Every added column should have a corresponding drop
        up_col_keys = {(c["table"], c["column_name"]) for c in mock_up.columns_added}
        down_col_keys = {(c["table"], c["column_name"]) for c in mock_down.columns_dropped}
        assert up_col_keys == down_col_keys
